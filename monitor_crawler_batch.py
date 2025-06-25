import time
import csv
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def crawl_monitor_list(crawling_url, max_page=20):
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

    for i in range(1, max_page + 1):
        print(f"🔍 {i}페이지 크롤링 중...")
        wait.until(EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover')))
        time.sleep(1)

        products = driver.find_elements(By.XPATH, '//ul[@class="product_list"]/li')

        for product in products:
            try:
                if not product.get_attribute("id") or "ad" in product.get_attribute("id"):
                    continue
                product_id = product.get_attribute("id").replace("productItem", "")
                model_name = product.find_element(By.XPATH, './div/div[2]/p/a').text.strip()

                # 가격 파싱 시도 (2가지 구조 대응)
                price = "가격없음"
                try:
                    # 방법 1: 대표 가격 (단일 strong 태그)
                    price = product.find_element(By.CSS_SELECTOR, 'p.price_sect strong').text.replace(",", "").strip()
                except:
                    try:
                        # 방법 2: 다중 쇼핑몰 가격 중 첫 번째 가격
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
                driver.find_element(By.XPATH, f'//a[@class="num "][{i%10}]').click()
        except:
            print("🔚 다음 페이지 없음")
            break

    driver.quit()

    df = pd.DataFrame(results)
    df.to_csv("monitor_list.csv", index=False, encoding="utf-8-sig")
    print("✅ monitor_list.csv 저장 완료")

if __name__ == "__main__":
    url = "https://prod.danawa.com/list/?cate=112757"
    crawl_monitor_list(url)