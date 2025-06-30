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
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(3)
    return driver

def get_products(driver):
    wait = WebDriverWait(driver, 10)
    wait.until(EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover')))
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

            # 가격 파싱
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

def crawl_monitor_list(crawling_url, max_page=150):
    driver = setup_driver()
    driver.get(crawling_url)
    time.sleep(2)

    try:
        driver.find_element(By.XPATH, '//option[@value="90"]').click()
    except:
        print("❌ '90개 보기' 클릭 실패")

    total_results = []
    seen_ids = set()

    for tab_name, tab_xpath in [("NEW", '//li[@data-sort-method="NEW"]'), ("BEST", '//li[@data-sort-method="BEST"]')]:
        try:
            driver.find_element(By.XPATH, tab_xpath).click()
            time.sleep(2)

            for page in range(1, max_page + 1):
                print(f"[{tab_name}] 📄 {page}페이지 크롤링 중...")

                products = get_products(driver)

                new_count = 0
                for item in products:
                    if item['상품코드'] not in seen_ids:
                        total_results.append(item)
                        seen_ids.add(item['상품코드'])
                        new_count += 1

                if new_count == 0:
                    print(f"🔚 [{tab_name}] 중복 상품으로 중단")
                    break

                try:
                    pagination_buttons = driver.find_elements(By.CSS_SELECTOR, 'div.number_wrap a.num')
                    for btn in pagination_buttons:
                        if btn.text == str(page + 1):
                            btn.click()
                            break
                    else:
                        raise Exception("페이지 버튼 없음")
                except:
                    print(f"🔚 [{tab_name}] 다음 페이지 없음")
                    break
        except Exception as e:
            print(f"❌ [{tab_name}] 탭 클릭 실패: {e}")
            continue

    driver.quit()

    with open("monitor_list.csv", 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['상품코드', '모델명', '가격'])
        for row in sorted(total_results, key=lambda x: x['모델명']):
            writer.writerow([row['상품코드'], row['모델명'], row['가격']])

    print(f"✅ monitor_list.csv 저장 완료 - 총 {len(total_results)}개")

if __name__ == "__main__":
    url = "https://prod.danawa.com/list/?cate=112757"
    crawl_monitor_list(url)
