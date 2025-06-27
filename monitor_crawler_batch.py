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
    wait = WebDriverWait(driver, 10)

    driver.get(crawling_url)
    time.sleep(2)

    # 페이지당 90개 출력 설정
    try:
        driver.find_element(By.XPATH, '//option[@value="90"]').click()
        wait.until(EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover')))
    except:
        print("❌ 90개 설정 실패")
        driver.quit()
        return

    results = []
    seen_ids = set()

    for i in range(1, max_page + 1):
        print(f"📄 {i}페이지 크롤링 중...")
        try:
            wait.until(EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover')))
            time.sleep(1)

            products = driver.find_elements(By.XPATH, '//ul[@class="product_list"]/li')

            for product in products:
                try:
                    if not product.get_attribute("id") or "ad" in product.get_attribute("id"):
                        continue

                    product_id = product.get_attribute("id").replace("productItem", "")
                    if product_id in seen_ids:
                        continue
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
                    print("⚠️ 제품 파싱 중 오류:", str(e))
                    continue

            # 다음 페이지 이동 시도
            try:
                next_button = driver.find_element(By.XPATH, f'//a[@class="num " and text()="{i + 1}"]')
                next_button.click()
            except:
                try:
                    driver.find_element(By.XPATH, '//a[@class="edge_nav nav_next"]').click()
                except:
                    print("🔚 마지막 페이지 도달 또는 더 이상 페이지 없음")
                    break

        except Exception as e:
            print(f"❌ {i}페이지 로딩 실패: {str(e)}")
            break

    driver.quit()

    df = pd.DataFrame(results)
    df.to_csv("monitor_list.csv", index=False, encoding="utf-8-sig")
    print(f"✅ 총 {len(df)}개 제품 저장 완료 → monitor_list.csv")

if __name__ == "__main__":
    url = "https://prod.danawa.com/list/?cate=112757"
    crawl_monitor_list(url)
