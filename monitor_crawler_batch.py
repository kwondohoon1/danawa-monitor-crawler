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
    wait = WebDriverWait(driver, 15)

    driver.get(crawling_url)
    time.sleep(2)

    # 90개 보기 선택
    try:
        view_90 = driver.find_element(By.XPATH, '//option[@value="90"]')
        driver.execute_script("arguments[0].selected = true; arguments[0].dispatchEvent(new Event('change'))", view_90)
        time.sleep(2)
        wait.until(EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover')))
    except:
        print("⚠️ 90개 보기 실패")

    results = []
    seen_ids = set()

    current_page = 1
    while current_page <= max_page:
        print(f"📄 {current_page}페이지 크롤링 중...")

        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'product_list')))
        except:
            print("❌ 제품 리스트 로딩 실패")
            break

        products = driver.find_elements(By.XPATH, '//ul[@class="product_list"]/li')

        for product in products:
            try:
                pid = product.get_attribute("id")
                if not pid or "ad" in pid:
                    continue
                pid = pid.replace("productItem", "")
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)

                model_name = product.find_element(By.XPATH, './div/div[2]/p/a').text.strip()
                price = "가격없음"
                try:
                    price = product.find_element(By.CSS_SELECTOR, 'p.price_sect strong').text.replace(",", "").strip()
                except:
                    try:
                        price = product.find_element(By.CSS_SELECTOR, 'ul > li.mall_list_item > a > p.price_sect > strong').text.replace(",", "").strip()
                    except:
                        pass

                results.append({
                    "상품코드": pid,
                    "모델명": model_name,
                    "가격": price
                })
            except Exception as e:
                print(f"❌ 제품 처리 실패: {e}")
                continue

        # 다음 페이지로 이동
        try:
            next_btn = driver.find_element(By.XPATH, '//a[@class="edge_nav nav_next"]')
            if "disabled" in next_btn.get_attribute("class"):
                print("🔚 마지막 페이지 도달")
                break
            else:
                driver.execute_script("arguments[0].click()", next_btn)
                time.sleep(2)
                wait.until(EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover')))
                current_page += 1
        except:
            print("❌ 다음 페이지 클릭 실패")
            break

    driver.quit()
    df = pd.DataFrame(results)
    df.drop_duplicates(subset=["상품코드"], inplace=True)
    df.to_csv("monitor_list.csv", index=False, encoding="utf-8-sig")
    print(f"✅ 총 {len(df)}개 제품 저장 완료")

if __name__ == "__main__":
    url = "https://prod.danawa.com/list/?cate=112757"
    crawl_monitor_list(url)
