import time
import csv
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def crawl_monitor_list(crawling_url, max_page=60):
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 10)

    driver.get(crawling_url)
    time.sleep(2)

    driver.find_element(By.XPATH, '//option[@value="90"]').click()
    wait.until(EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover')))

    results = []
    seen_ids = set()  # 중복 방지를 위한 상품코드 집합

    for i in range(1, max_page + 1):
        print(f"🔍 {i}페이지 크롤링 중...")
        wait.until(EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover')))
        time.sleep(1.5)

        products = driver.find_elements(By.XPATH, '//ul[@class="product_list"]/li')

        for product in products:
            try:
                product_raw_id = product.get_attribute("id")
                if not product_raw_id or "ad" in product_raw_id:
                    continue

                product_id = product_raw_id.replace("productItem", "")

                # 이미 수집된 제품이면 스킵
                if product_id in seen_ids:
                    continue
                seen_ids.add(product_id)

                model_name = product.find_element(By.XPATH, './div/div[2]/p/a').text.strip()

                # 가격 파싱 시도 (2가지 구조 대응)
                price = "가격없음"
                try:
                    price = product.find_element(By.CSS_SELECTOR, 'p.price_sect strong').text.replace(",", "").strip()
                except:
                    try:
                        price = product.find_element(By.CSS_SELECTOR, 'ul > li.mall_list_item > a > p.price_sect > strong').text.replace(",", "").strip()
                    except:
                        pass

                results.append({
                    "상품코드": product_id,
                    "모델명": model_name,
                    "가격": price
                })
            except:
                continue

        # 페이지 이동
        try:
            if i % 10 == 0:
                driver.find_element(By.XPATH, '//a[@class="edge_nav nav_next"]').click()
            else:
                # 페이지 번호는 1~10 사이만 존재하므로 예외 처리
                page_index = i % 10 if i % 10 != 0 else 10
                driver.find_element(By.XPATH, f'(//a[@class="num " or @class="num on"])[{page_index}]').click()
        except:
            print("🔚 다음 페이지 없음")
            break

    driver.quit()

    df = pd.DataFrame(results)
    df.drop_duplicates(subset=["상품코드"], inplace=True)  # 혹시라도 중복된 것 제거
    df.to_csv("monitor_list.csv", index=False, encoding="utf-8-sig")
    print(f"✅ monitor_list.csv 저장 완료 - 총 {len(df)}개 제품")

if __name__ == "__main__":
    url = "https://prod.danawa.com/list/?cate=112757"
    crawl_monitor_list(url)
