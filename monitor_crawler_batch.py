# -*- coding: utf-8 -*-
import csv, os, time, traceback
from datetime import datetime, timedelta
from pytz import timezone
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

CRAWLING_DATA_CSV_FILE = 'CrawlingCategory.csv'
DATA_PATH = 'crawl_data'
TIMEZONE = 'Asia/Seoul'
DATA_PRODUCT_DIVIDER = '|'
DATA_ROW_DIVIDER = '_'

def now():
    return datetime.now(timezone(TIMEZONE)).strftime('%Y-%m-%d %H:%M:%S')

def get_crawling_targets():
    categories = []
    with open(CRAWLING_DATA_CSV_FILE, 'r', newline='') as f:
        for row in csv.reader(f):
            if not row[0].startswith('//'):
                categories.append({
                    'name': row[0],
                    'url': row[1],
                    'page_size': int(row[2])
                })
    return categories

def setup_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument("lang=ko_KR")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def crawl_category(category):
    name = category['name']
    url = category['url']
    page_size = category['page_size']
    out_file = f'{DATA_PATH}/{name}.csv'
    os.makedirs(DATA_PATH, exist_ok=True)

    with open(out_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Id', 'Name', 'Price', 'CrawlTime'])

        try:
            driver = setup_driver()
            driver.get(url)

            sort_methods = ['NEW', 'BEST']
            for sort in sort_methods:
                try:
                    driver.find_element(By.XPATH, f'//li[@data-sort-method="{sort}"]').click()
                    time.sleep(2)
                except:
                    continue

                for page in range(1, page_size + 1):
                    try:
                        paged_url = f"{url}&sort={sort}&page={page}"
                        driver.get(paged_url)
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "ul.product_list li.prod_item"))
                        )
                        time.sleep(1.5)
                        products = driver.find_elements(By.CSS_SELECTOR, "ul.product_list li.prod_item")

                        for product in products:
                            pid = product.get_attribute("id")
                            if not pid or pid.startswith("ad") or "prod_ad_item" in product.get_attribute("class"):
                                continue

                            productId = pid.replace("productItem_", "")
                            try:
                                name_el = product.find_element(By.CSS_SELECTOR, 'div.prod_info p.prod_name a')
                                productName = name_el.text.strip()
                            except:
                                continue

                            priceStr = ''
                            try:
                                price_uls = product.find_elements(By.CSS_SELECTOR, 'div.prod_pricelist ul li')
                                for priceBlock in price_uls:
                                    if 'top5_button' in priceBlock.get_attribute('class'):
                                        continue
                                    mallName = priceBlock.find_element(By.CSS_SELECTOR, 'a div.prod_mall_area').text.strip()
                                    price = priceBlock.find_element(By.CSS_SELECTOR, 'a div.prod_price span.price_sect em').text.strip()
                                    priceStr += f'{mallName}{DATA_ROW_DIVIDER}{price}{DATA_PRODUCT_DIVIDER}'
                                priceStr = priceStr.strip(DATA_PRODUCT_DIVIDER)
                            except:
                                priceStr = ''

                            writer.writerow([productId, productName, priceStr, now()])
                    except Exception as e:
                        print(f"⚠️ 페이지 {page} 오류: {e}")
                        continue
            driver.quit()

        except Exception as e:
            print(f"❌ 크롤링 실패 - {name}")
            print(traceback.format_exc())

if __name__ == '__main__':
    categories = get_crawling_targets()
    for category in categories:
        print(f'🚀 Start crawling: {category["name"]}')
        crawl_category(category)
        print(f'✅ Finished: {category["name"]}\n')
