import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def crawl_monitor_list(crawling_url, max_page=100):
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 10)

    driver.get(crawling_url)
    time.sleep(2)

    # 1페이지 90개로 설정
    try:
        driver.find_element(By.XPATH, '//option[@value="90"]').click()
        wait.until(EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover')))
    except:
        print("⚠️ 90개 보기 설정 실패")

    results = []
    seen_ids = set()

    for i in range(1, max_page + 1):
        print(f"🔍 {i}페이지 크롤링 중...")

        try:
            wait.until(EC.presence_of_all_elements_located((By.XPATH, '//ul[@class="product_list"]/li')))
            products = driver.find_elements(By.XPATH, '//ul[@class="product_list"]/li')
        except:
            print("⚠️ 제품 리스트 로딩 실패")
            continue

        for product in products:
            try:
                if not product.get_attribute("id") or "ad" in product.get_attribute("id"):
                    continue

                product_id = product.get_attribute("id").replace("productItem", "")
                if product_id in seen_ids:
                    continue  # 중복 제거
                seen_ids.add(product_id)

                model_name = product.find_element(By.XPATH, './div/div[2]/p/a').text.strip()

                # 가격 파싱
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

            except Exception as e:
                print(f"❌ 항목 처리 실패: {e}")
                continue

        # 페이지 이동
        try:
            next_button = driver.find_element(By.XPATH, f'//a[@class="num " and text()="{(i % 10) + 1}"]')
            next_button.click()
            time.sleep(1)
        except:
            try:
                driver.find_element(By.XPATH, '//a[@class="edge_nav nav_next"]').click()
                time.sleep(1)
            except:
                print("🔚 다음 페이지 없음")
                break

    driver.quit()

    df = pd.DataFrame(results)
    df.drop_duplicates(subset='상품코드', inplace=True)
    df.to_csv("monitor_list.csv", index=False, encoding="utf-8-sig")
    print(f"✅ monitor_list.csv 저장 완료 (총 {len(df)}개)")
