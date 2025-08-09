import sys
import argparse
import csv
import time
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
import os
import subprocess


def get_navigation_timing(driver):
    script = """
    var performance = window.performance || window.mozPerformance || window.msPerformance || window.webkitPerformance;
    if (performance && performance.timing) {
        return performance.timing.loadEventEnd - performance.timing.fetchStart;
    }
    return -1;
    """
    try:
        result = driver.execute_script(script)
        if result >= 0:
            return result / 1000.0
        return None
    except:
        return None


def is_same_domain(url1, url2):
    return urlparse(url1).netloc == urlparse(url2).netloc


def get_internal_links(driver, base_url):
    links = []
    try:
        for a in driver.find_elements(By.TAG_NAME, "a"):
            href = a.get_attribute("href")
            if href and is_same_domain(base_url, href):
                links.append(href)
    except:
        pass
    return list(set(links))


def find_yandex_browser():
    system = sys.platform
    paths = []

    if system == "win32":
        user = os.getenv("USERPROFILE")
        if user:
            paths.append(os.path.join(user, "AppData", "Local", "Yandex", "YandexBrowser", "application", "browser.exe"))
        pf = os.getenv("PROGRAMFILES")
        if pf:
            paths.append(os.path.join(pf, "Yandex", "YandexBrowser", "application", "browser.exe"))
        pf86 = os.getenv("PROGRAMFILES(X86)")
        if pf86:
            paths.append(os.path.join(pf86, "Yandex", "YandexBrowser", "application", "browser.exe"))

    for path in paths:
        if os.path.isfile(path):
            return path
    return None


def create_driver(browser):
    print(f"Запуск браузера: {browser}")

    if browser == "chrome":
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

    elif browser == "yandex":
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        path = find_yandex_browser()
        if not path:
            raise Exception("Не могу найти Яндекс.Браузер.")
        print(f"Нашёл браузер: {path}")
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.binary_location = path
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

    elif browser == "firefox":
        from selenium.webdriver.firefox.service import Service
        from selenium.webdriver.firefox.options import Options
        options = Options()
        options.add_argument("--headless")
        service = Service(GeckoDriverManager().install())
        return webdriver.Firefox(service=service, options=options)

    else:
        raise Exception(f"Нет такого браузера: {browser}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("top_n")
    parser.add_argument("--no-first-page", action="store_true")
    parser.add_argument("--save-csv", metavar="FILE")
    parser.add_argument("--browser", choices=["chrome", "yandex", "firefox"], default="chrome")
    args = parser.parse_args()

    if args.top_n == "all":
        top_n = None
    else:
        try:
            top_n = int(args.top_n)
            if top_n <= 0:
                print("top_n должен быть > 0")
                sys.exit(1)
        except:
            print("top_n — число или 'all'")
            sys.exit(1)

    try:
        driver = create_driver(args.browser)
    except Exception as e:
        print(f"Ошибка браузера: {e}")
        sys.exit(1)

    try:
        url = args.url
        if not urlparse(url).scheme:
            url = "https://" + url

        print(f"Иду на: {url}")
        driver.get(url)
        time.sleep(2)

        domain = urlparse(driver.current_url).netloc
        print(f"Домен: {domain}")

        all_pages = {}
        first_links = {}

        links_on_first = get_internal_links(driver, url)
        print(f"Ссылок на первой странице: {len(links_on_first)}")

        if not args.no_first_page:
            print("\n--- Проверка ссылок со стартовой страницы ---")
            for link in links_on_first:
                try:
                    driver.get(link)
                    t = get_navigation_timing(driver)
                    if t is not None:
                        first_links[link] = t
                        all_pages[link] = t
                        print(f"{link} -> {t:.3f} с")
                    else:
                        all_pages[link] = float('inf')
                except:
                    all_pages[link] = float('inf')

        print("\n--- Проверка других страниц ---")
        queue = links_on_first[:]
        visited = set(all_pages.keys())

        while queue:
            link = queue.pop(0)
            if link in visited:
                continue

            try:
                driver.get(link)
                time.sleep(1)
                t = get_navigation_timing(driver)
                if t is not None:
                    all_pages[link] = t
                    print(f"[{len(all_pages)}] {link} -> {t:.3f} с")
                else:
                    all_pages[link] = float('inf')

                new_links = get_internal_links(driver, domain)
                for l in new_links:
                    if l not in visited:
                        queue.append(l)
                visited.add(link)
            except Exception as e:
                print(f"Ошибка на {link}: {str(e)[:50]}...")
                all_pages[link] = float('inf')
                visited.add(link)

        real_pages = {k: v for k, v in all_pages.items() if v != float('inf')}
        sorted_pages = sorted(real_pages.items(), key=lambda x: x[1], reverse=True)

        if top_n:
            sorted_pages = sorted_pages[:top_n]

        print("\n" + "="*60)
        print("ТОП медленных страниц")
        print("="*60)
        print(f"{'#':<4} {'Время':<10} {'Адрес'}")
        print("-"*60)
        for i, (url, t) in enumerate(sorted_pages, 1):
            print(f"{i:<4} {t:<10.3f} {url}")

        if not args.no_first_page and first_links:
            print("\n--- Ссылки с первой страницы ---")
            for url, t in sorted(first_links.items(), key=lambda x: x[1], reverse=True):
                print(f"{t:.3f} с -> {url}")

        if args.save_csv:
            with open(args.save_csv, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["URL", "Load Time (s)"])
                for url, t in sorted_pages:
                    writer.writerow([url, f"{t:.3f}"])
            print(f"\nСохранено в {args.save_csv}")

    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()