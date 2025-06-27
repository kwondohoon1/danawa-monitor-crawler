import time
import csv
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def crawl_monitor_list(crawling_url, max_page=200):
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 15)

    driver.get(crawling_url)
    time.sleep(2)

    try:
        # 90개씩 보기 설정
        driver.find_element(By.XPATH, '//option[@value="90"]').click()
        wait.until(EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover')))
    except:
        print("⚠️ 90개 보기 선택 실패")

    results = []
    page = 1

    while page <= max_page:
        print(f"📄 {page}페이지 크롤링 중...")
        try:
            wait.until(EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover')))
            time.sleep(1)

            product_list = driver.find_elements(By.XPATH, '//ul[@class="product_list"]/li')
            for product in product_list:
                try:
                    pid = product.get_attribute("id")
                    if not pid or "ad" in pid:
                        continue

                    product_id = pid.replace("productItem", "")
                    model_name = product.find_element(By.XPATH, './div/div[2]/p/a').text.strip()

                    # 가격 추출
                    price = "가격없음"
                    try:
                        price_elem = product.find_element(By.CSS_SELECTOR, 'p.price_sect strong')
                        price = price_elem.text.replace(",", "").strip()
                    except:
                        try:
                            price_elem = product.find_element(By.CSS_SELECTOR, 'ul > li.mall_list_item > a > p.price_sect > strong')
                            price = price_elem.text.replace(",", "").strip()
                        except:
                            pass

                    results.append({
                        "상품코드": product_id,
                        "모델명": model_name,
                        "가격": price
                    })
                except Exception as e:
                    continue

            # 다음 페이지 클릭
            if page % 10 == 0:
                next_btn = driver.find_element(By.XPATH, '//a[@class="edge_nav nav_next"]')
                next_btn.click()
            else:
                page_btn = driver.find_element(By.XPATH, f'//a[@class="num "][{(page % 10) or 10}]')
                page_btn.click()

            page += 1

        except Exception as e:
            print(f"❌ {page}페이지 크롤링 실패: {str(e)}")
            break

    driver.quit()

    # 중복 제거
    df = pd.DataFrame(results)
    df = df.drop_duplicates(subset=["상품코드"])
    df.to_csv("monitor_list.csv", index=False, encoding="utf-8-sig")
    print(f"✅ 총 {len(df)}개 제품 저장 완료")

if __name__ == "__main__":
    url = "https://prod.danawa.com/list/?cate=112757"
    crawl_monitor_list(url, max_page=200)
