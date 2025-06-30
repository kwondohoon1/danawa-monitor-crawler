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

            result.append({
                "상품코드": product_id,
                "모델명": model_name,
                "가격": price
            })
        except:
            continue

    return result

def crawl_monitor_list(url):
    driver = setup_driver()
    driver.get(url)
    time.sleep(2)

    try:
        driver.find_element(By.XPATH, '//option[@value="90"]').click()
    except:
        print("❌ '90개 보기' 클릭 실패")

    all_products = []
    seen_ids = set()

    # 정렬 기준을 순차적으로 바꿔가며 크롤링
    sort_methods = ['NEW', 'BEST', 'POPULAR', 'LOW_PRICE', 'HIGH_PRICE']
    sort_labels = {
        'NEW': '신상품순',
        'BEST': '판매량순',
        'POPULAR': '인기순',
        'LOW_PRICE': '낮은가격순',
        'HIGH_PRICE': '높은가격순',
    }

    for method in sort_methods:
        try:
            print(f"\n🔄 정렬 기준: {sort_labels[method]}")

            driver.find_element(By.XPATH, f'//li[@data-sort-method="{method}"]').click()
            time.sleep(2)

            for page in range(1, 11):  # 1~10페이지
                print(f"📄 {method} - {page}페이지")

                products = get_products(driver)
                new_count = 0
                for item in products:
                    if item['상품코드'] not in seen_ids:
                        seen_ids.add(item['상품코드'])
                        all_products.append(item)
                        new_count += 1

                if new_count == 0:
                    print("🔚 중복 상품만 나와서 중단")
                    break

                # 페이지 이동
                try:
                    next_buttons = driver.find_elements(By.CSS_SELECTOR, 'div.number_wrap a.num')
                    for btn in next_buttons:
                        if btn.text == str(page + 1):
                            btn.click()
                            break
                    else:
                        break
                except:
                    break

        except Exception as e:
            print(f"❌ 정렬 {method} 실패: {e}")
            continue

    driver.quit()

    with open("monitor_list.csv", 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['상품코드', '모델명', '가격'])
        for row in sorted(all_products, key=lambda x: x['모델명']):
            writer.writerow([row['상품코드'], row['모델명'], row['가격']])

    print(f"\n✅ monitor_list.csv 저장 완료 - 총 {len(all_products)}개 수집됨")

if __name__ == "__main__":
    crawl_monitor_list("https://prod.danawa.com/list/?cate=112757")
