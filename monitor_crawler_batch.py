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
    sort_methods = ['NEW', 'BEST']
    for sort in sort_methods:
        try:
            driver.find_element(By.XPATH, f'//li[@data-sort-method="{sort}"]').click()
            wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, 'product_list_cover')))
        except:
            continue

        page = 1
        while page <= max_page:
            print(f"📄 {sort} 정렬 {page}페이지 크롤링 중...")
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

            try:
                next_btn = driver.find_element(By.CSS_SELECTOR, 'a.edge_nav.nav_next')
                if "disabled" in next_btn.get_attribute("class"):
                    break
                next_btn.click()
                page += 1
                time.sleep(2)
            except:
                try:
                    driver.find_element(By.LINK_TEXT, str(page + 1)).click()
                    page += 1
                    time.sleep(2)
                except:
                    break

    driver.quit()

    df = pd.DataFrame(results.values())
    df.to_csv("monitor_list.csv", index=False, encoding="utf-8-sig")
    print(f"✅ monitor_list.csv 저장 완료 (총 {len(df)}개 제품)")

if __name__ == "__main__":
    url = "https://prod.danawa.com/list/?cate=112757"
    crawl_monitor_list(url)
