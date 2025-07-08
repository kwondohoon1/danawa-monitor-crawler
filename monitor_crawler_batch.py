# -*- coding: utf-8 -*-
import csv, os, time, traceback
from datetime import datetime
from pytz import timezone
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

DATA_PATH = 'crawl_data'
TIMEZONE = 'Asia/Seoul'
DATA_PRODUCT_DIVIDER = '|'
DATA_ROW_DIVIDER = '_'
CATEGORY_NAME = 'Monitor'
CATEGORY_URL = 'https://prod.danawa.com/list/?cate=112757'
CRAWL_SORTS = ['NEW', 'BEST']
MAX_PAGE = 300  # 필요 시 더 증가 가능

def now():
    return datetime.now(timezone(TIMEZONE)).strftime('%Y-%m-%d %H:%M:%S')

def setup_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument("lang=ko_KR")
    return webdriver.Chrome(options=options)

def crawl_all_monitors():
    os.makedirs(DATA_PATH, exist_ok=True)
    output_file = os.path.join(DATA_PATH, f"{CATEGORY_NAME}.csv")

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Id', 'Name', 'Price', 'CrawlTime'])

        try:
            driver = setup_driver()
            crawled_ids = set()

            for sort in CRAWL_SORTS:
                for page in range(1, MAX_PAGE + 1):
                    paged_url = f"{CATEGORY_URL}&sort={sort}&page={page}"
                    try:
                        driver.get(paged_url)
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "ul.product_list li.prod_item"))
                        )
                        time.sleep(1.5)
                        products = driver.find_elements(By.CSS_SELECTOR, "ul.product_list li.prod_item")

                        if not products:
                            break

                        new_count = 0
                        for product in products:
                            pid = product.get_attribute("id")
                            if not pid or pid.startswith("ad") or "prod_ad_item" in product.get_attribute("class"):
                                continue

                            productId = pid.replace("productItem_", "")
                            if productId in crawled_ids:
                                continue

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
                            crawled_ids.add(productId)
                            new_count += 1

                        if new_count == 0:
                            break
                    except Exception as e:
                        print(f"⚠️ 페이지 {page} 오류: {e}")
                        continue
            driver.quit()

        except Exception:
            print(f"❌ 크롤링 실패")
            print(traceback.format_exc())

if __name__ == '__main__':
    print(f'🚀 Start crawling: {CATEGORY_NAME}')
    crawl_all_monitors()
    print(f'✅ Finished: {CATEGORY_NAME}')
