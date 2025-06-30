# monitor_crawler_batch.py

import time
import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def setup_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    return webdriver.Chrome(options=options)

def get_product_list(driver):
    WebDriverWait(driver, 10).until(
        EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover'))
    )
    time.sleep(1)

    products = driver.find_elements(By.XPATH, '//ul[@class="product_list"]/li')
    result = []

    for product in products:
        try:
            pid = product.get_attribute("id")
            if not pid or pid.startswith("ad") or "prod_ad_item" in product.get_attribute("class"):
                continue

            product_id = pid.replace("productItem", "")
            name = product.find_element(By.XPATH, './div/div[2]/p/a').text.strip()

            price = "0"
            try:
                price = product.find_element(By.CSS_SELECTOR, 'p.price_sect strong').text.replace(",", "").strip()
            except:
                try:
                    price = product.find_element(By.CSS_SELECTOR, 'ul > li.mall_list_item > a > p.price_sect > strong').text.replace(",", "").strip()
                except:
                    pass

            result.append((product_id, name, price))
        except:
            continue

    return result

def crawl_monitor_products(url, max_pages=200):
    driver = setup_driver()
    driver.get(url)
    time.sleep(2)

    try:
        driver.find_element(By.XPATH, '//option[@value="90"]').click()
    except:
        print("⚠️ '90개 보기' 클릭 실패")

    all_results = []
    seen_ids = set()

    for sort_method in ['NEW', 'BEST']:
        try:
            driver.find_element(By.XPATH, f'//li[@data-sort-method="{sort_method}"]').click()
            time.sleep(2)

            for page_index in range(-1, max_pages):
                print(f"[{sort_method}] 페이지 {page_index+1 if page_index >= 0 else '초기'} 수집 중...")

                if page_index >= 0:
                    try:
                        if page_index % 10 == 0 and page_index != 0:
                            driver.find_element(By.XPATH, '//a[@class="edge_nav nav_next"]').click()
                        else:
                            page_buttons = driver.find_elements(By.CSS_SELECTOR, 'div.number_wrap a.num')
                            for btn in page_buttons:
                                if btn.text == str((page_index % 10) + 1):
                                    btn.click()
                                    break
                    except:
                        print(f"⚠️ {sort_method} 페이지 {page_index+1} 이동 실패")
                        break

                products = get_product_list(driver)
                new_count = 0
                for pid, name, price in products:
                    if pid not in seen_ids:
                        seen_ids.add(pid)
                        all_results.append((pid, name, price))
                        new_count += 1

                if new_count == 0:
                    print(f"🔚 {sort_method} - 중복으로 더 이상 수집 없음")
                    break

        except Exception as e:
            print(f"❌ 정렬 '{sort_method}' 처리 실패: {e}")
            continue

    driver.quit()

    with open('monitor_list.csv', 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['상품코드', '모델명', '가격'])
        for row in sorted(all_results, key=lambda x: x[1]):
            writer.writerow(row)

    print(f"\n✅ monitor_list.csv 저장 완료: 총 {len(all_results)}개 수집됨")

if __name__ == '__main__':
    crawl_monitor_products("https://prod.danawa.com/list/?cate=112757", max_pages=200)
