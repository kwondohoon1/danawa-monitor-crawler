# -*- coding: utf-8 -*-

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import csv
import time
import os

TARGET_URL = 'https://prod.danawa.com/list/?cate=112757'
OUTPUT_FILE = 'monitor_list.csv'

def setup_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(3)
    return driver

def get_products(driver):
    WebDriverWait(driver, 10).until(EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover')))
    time.sleep(1)

    products = driver.find_elements(By.XPATH, '//ul[@class="product_list"]/li')
    result = []

    for product in products:
        try:
            pid = product.get_attribute("id")
            if not pid or "ad" in pid:
                continue
            product_id = pid.replace("productItem", "")
            model_name = product.find_element(By.XPATH, './div/div[2]/p/a').text.strip()

            price = "가격없음"
            try:
                price = product.find_element(By.CSS_SELECTOR, 'p.price_sect strong').text.replace(",", "").strip()
            except:
                try:
                    price = product.find_element(By.CSS_SELECTOR, 'ul > li.mall_list_item > a > p.price_sect > strong').text.replace(",", "").strip()
                except:
                    pass

            result.append([product_id, model_name, price])
        except:
            continue
    return result

def crawl_monitor_list(url, max_page=150):
    driver = setup_driver()
    driver.get(url)
    time.sleep(2)

    try:
        driver.find_element(By.XPATH, '//option[@value="90"]').click()
    except:
        print("❌ '90개 보기' 클릭 실패")

    all_products = []
    seen_ids = set()

    for tab_xpath in ['//li[@data-sort-method="NEW"]', '//li[@data-sort-method="BEST"]']:
        try:
            driver.find_element(By.XPATH, tab_xpath).click()
            time.sleep(2)

            for page in range(1, max_page + 1):
                print(f"[{tab_xpath}] 📄 {page}페이지 크롤링 중...")

                products = get_products(driver)

                new_count = 0
                for item in products:
                    if item[0] not in seen_ids:
                        all_products.append(item)
                        seen_ids.add(item[0])
                        new_count += 1

                if new_count == 0:
                    break

                try:
                    if page % 10 == 0:
                        driver.find_element(By.XPATH, '//a[@class="edge_nav nav_next"]').click()
                    else:
                        driver.find_element(By.XPATH, f'//a[@class="num "][{page % 10}]').click()
                except:
                    break
        except:
            continue

    driver.quit()

    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['상품코드', '모델명', '가격'])
        for row in sorted(all_products, key=lambda x: x[1]):
            writer.writerow(row)

    print(f"✅ monitor_list.csv 저장 완료 - 총 {len(all_products)}개")

if __name__ == "__main__":
    crawl_monitor_list(TARGET_URL)
