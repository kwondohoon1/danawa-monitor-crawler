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
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--no-sandbox')
    return webdriver.Chrome(options=options)

def remove_ads_and_extract(driver):
    WebDriverWait(driver, 10).until(
        EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover'))
    )
    time.sleep(1)

    results = []
    products = driver.find_elements(By.XPATH, '//ul[@class="product_list"]/li')
    for product in products:
        try:
            pid = product.get_attribute("id")
            if not pid or pid.startswith("ad") or "prod_ad_item" in product.get_attribute("class"):
                continue
            product_id = pid.replace("productItem", "")
            model_name = product.find_element(By.XPATH, './div/div[2]/p/a').text.strip()
            price = "0"
            try:
                price = product.find_element(By.CSS_SELECTOR, 'p.price_sect strong').text.replace(",", "").strip()
            except:
                try:
                    price = product.find_element(By.CSS_SELECTOR, 'ul > li.mall_list_item > a > p.price_sect > strong').text.replace(",", "").strip()
                except:
                    pass

            results.append((product_id, model_name, price))
        except:
            continue
    return results

def crawl_all_monitors(url, crawling_page_size=200):
    driver = setup_driver()
    driver.get(url)
    time.sleep(2)

    # 90개씩 보기 설정
    try:
        driver.find_element(By.XPATH, '//option[@value="90"]').click()
    except:
        print("⚠️ '90개 보기' 클릭 실패")

    seen_ids = set()
    final_results = []

    # NEW → BEST 순서로 순회
    for idx, sort_method in enumerate(["NEW", "BEST"]):
        try:
            print(f"\n🔁 정렬: {sort_method}")
            if idx == 0:
                driver.find_element(By.XPATH, '//li[@data-sort-method="NEW"]').click()
            else:
                driver.find_element(By.XPATH, '//li[@data-sort-method="BEST"]').click()
            time.sleep(2)

            for page in range(-1, crawling_page_size):  # -1 = 첫 정렬 클릭 후, 0~N까지 페이지 이동
                print(f"  📄 페이지 {page+1 if page >= 0 else '초기'}")
                if page >= 0:
                    try:
                        if page % 10 == 0 and page != 0:
                            driver.find_element(By.XPATH, '//a[@class="edge_nav nav_next"]').click()
                        else:
                            page_buttons = driver.find_elements(By.CSS_SELECTOR, 'div.number_wrap a.num')
                            for btn in page_buttons:
                                if btn.text == str((page % 10) + 1):
                                    btn.click()
                                    break
                    except:
                        print("  ⛔ 페이지 버튼 클릭 실패")
                        break

                products = remove_ads_and_extract(driver)
                for pid, name, price in products:
                    if pid not in seen_ids:
                        seen_ids.add(pid)
                        final_results.append((pid, name, price))

        except Exception as e:
            print(f"⚠️ 정렬 '{sort_method}' 중 에러 발생: {e}")
            continue

    driver.quit()

    # 저장
    with open('monitor_list.csv', 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['상품코드', '모델명', '가격'])
        for row in sorted(final_results, key=lambda x: x[1]):
            writer.writerow(row)

    print(f"\n✅ monitor_list.csv 저장 완료: 총 {len(final_results)}개 상품")

if __name__ == '__main__':
    crawl_all_monitors("https://prod.danawa.com/list/?cate=112757", crawling_page_size=200)
