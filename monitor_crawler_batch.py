import time
import csv
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
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("lang=ko_KR")
    options.add_argument("user-agent=Mozilla/5.0")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 10)

    driver.get(crawling_url)
    time.sleep(2)

    try:
        driver.find_element(By.XPATH, '//option[@value="90"]').click()
        wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, 'product_list_cover')))
    except:
        pass

    results = {}

    # 실제 신상품 정렬은 '신상품순' 필터 클릭 필요 (예: 정렬 기준 = 등록일)
    try:
        sort_button = driver.find_element(By.XPATH, '//li[@data-sort-method="releaseDate"]')
        sort_button.click()
        wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, 'product_list_cover')))
        print("🔀 정렬기준: 신상품순 (등록일 순)")
    except:
        print("⚠️ 신상품순 정렬 실패, 기본 정렬 유지")

    page = 1
    while page <= max_page:
        print(f"📄 {page}페이지 크롤링 중...")
        try:
            wait.until(EC.presence_of_all_elements_located((By.XPATH, '//ul[@class="product_list"]/li')))
        except:
            print("⏳ 로딩 실패")
            break

        time.sleep(1)
        products = driver.find_elements(By.XPATH, '//ul[@class="product_list"]/li')

        for product in products:
            try:
                pid = product.get_attribute("id")
                if not pid or "ad" in pid:
                    continue
                product_id = pid.replace("productItem", "")
                if product_id in results:
                    continue

                model_name = product.find_element(By.XPATH, './div/div[2]/p/a').text.strip()

                price = "가격없음"
                try:
                    price = product.find_element(By.CSS_SELECTOR, 'p.price_sect strong').text.replace(",", "").strip()
                except:
                    try:
                        price = product.find_element(By.CSS_SELECTOR, 'ul > li.mall_list_item > a > p.price_sect > strong').text.replace(",", "").strip()
                    except:
                        pass

                results[product_id] = {
                    "상품코드": product_id,
                    "모델명": model_name,
                    "가격": price
                }
            except:
                continue

        # AJAX 기반 페이지 전환: 페이지 번호 버튼 클릭
        try:
            page_buttons = driver.find_elements(By.XPATH, '//a[contains(@class, "num")]')
            for btn in page_buttons:
                if btn.text.strip() == str(page + 1):
                    btn.click()
                    page += 1
                    time.sleep(2)
                    break
            else:
                break  # 다음 페이지 번호가 없으면 종료
        except:
            break

    driver.quit()

    df = pd.DataFrame(results.values())
    df.to_csv("monitor_list.csv", index=False, encoding="utf-8-sig")
    print(f"✅ monitor_list.csv 저장 완료 (총 {len(df)}개 제품)")

if __name__ == "__main__":
    url = "https://prod.danawa.com/list/?cate=112757"
    crawl_monitor_list(url)
