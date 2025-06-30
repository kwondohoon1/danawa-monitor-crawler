import time
import csv
import pandas as pd
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
    options.add_argument('lang=ko_KR')
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(3)
    return driver

def click_element_when_ready(driver, by, value, timeout=15):
    try:
        WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )
        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover'))
        )
        element = driver.find_element(by, value)
        driver.execute_script("arguments[0].click();", element)
        time.sleep(1.5)
    except Exception as e:
        print(f"❌ 클릭 실패: {value} - {e}")

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
            if 'prod_ad_item' in product.get_attribute('class'):
                continue

            product_id = pid.replace("productItem", "")
            model_name = product.find_element(By.XPATH, './div/div[2]/p/a').text.strip()

            # 가격 파싱
            price = "가격없음"
            price_area = product.find_elements(By.CSS_SELECTOR, 'ul > li.mall_list_item')
            price_list = []

            if price_area:
                for item in price_area:
                    try:
                        mall = item.find_element(By.CSS_SELECTOR, 'div > a > div.mall_name').text.strip()
                        val = item.find_element(By.CSS_SELECTOR, 'div > a > div.price_sect > em').text.strip().replace(",", "")
                        price_list.append(f"{mall}:{val}")
                    except:
                        continue
                price = " | ".join(price_list) if price_list else "가격없음"
            else:
                try:
                    price = product.find_element(By.CSS_SELECTOR, 'p.price_sect strong').text.replace(",", "").strip()
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

def crawl_monitor_list(crawling_url, max_page=25):
    driver = setup_driver()
    driver.get(crawling_url)
    time.sleep(2)

    try:
        click_element_when_ready(driver, By.XPATH, '//option[@value="90"]')
    except:
        print("❌ '90개 보기' 클릭 실패")

    total_results = []
    seen_ids = set()

    # 탭별로 크롤링
    for tab_name, tab_xpath in [("NEW", '//li[@data-sort-method="NEW"]'), ("BEST", '//li[@data-sort-method="BEST"]')]:
        try:
            click_element_when_ready(driver, By.XPATH, tab_xpath)

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
                    if page % 10 == 0:
                        click_element_when_ready(driver, By.XPATH, '//a[@class="edge_nav nav_next"]')
                    else:
                        click_element_when_ready(driver, By.XPATH, f'//a[@class="num "][{page % 10}]')
                except:
                    print(f"🔚 [{tab_name}] 다음 페이지 없음")
                    break
        except Exception as e:
            print(f"❌ [{tab_name}] 탭 클릭 실패: {e}")
            continue

    driver.quit()

    df = pd.DataFrame(total_results)
    df.to_csv("monitor_list.csv", index=False, encoding="utf-8-sig")
    print(f"✅ monitor_list.csv 저장 완료 - 총 {len(df)}개")

if __name__ == "__main__":
    url = "https://prod.danawa.com/list/?cate=112757"
    crawl_monitor_list(url)
