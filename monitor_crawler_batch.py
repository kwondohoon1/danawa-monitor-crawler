import time
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

def wait_for_list_ready(driver):
    WebDriverWait(driver, 10).until(
        EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover'))
    )
    time.sleep(1)

def get_total_pages(driver):
    try:
        pages = driver.find_elements(By.CSS_SELECTOR, 'div.number_wrap a.num')
        page_numbers = [int(p.text.strip()) for p in pages if p.text.strip().isdigit()]
        return max(page_numbers) if page_numbers else 1
    except:
        return 1

def get_products(driver):
    wait_for_list_ready(driver)
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

            # 대표 가격만 추출
            price = "가격없음"
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

def go_to_page(driver, page_number):
    try:
        current_page_el = driver.find_element(By.CSS_SELECTOR, 'div.number_wrap a.num.on')
        current_page = int(current_page_el.text.strip())
    except:
        current_page = -1

    if page_number == current_page:
        return

    try:
        pages = driver.find_elements(By.CSS_SELECTOR, 'div.number_wrap a.num')
        for p in pages:
            if p.text.strip() == str(page_number):
                driver.execute_script("arguments[0].click();", p)
                wait_for_list_ready(driver)
                return
        driver.find_element(By.CSS_SELECTOR, 'div.number_wrap a.edge_nav.nav_next').click()
        wait_for_list_ready(driver)
        go_to_page(driver, page_number)
    except:
        pass

def crawl_monitor_list_all(url):
    driver = setup_driver()
    driver.get(url)
    time.sleep(2)

    try:
        driver.find_element(By.XPATH, '//option[@value="90"]').click()
        wait_for_list_ready(driver)
    except:
        print("❌ '90개 보기' 클릭 실패")

    seen_ids = set()
    total_results = []

    total_pages = get_total_pages(driver)
    print(f"📌 전체 페이지 수: {total_pages}")

    for page in range(1, total_pages + 1):
        print(f"📄 {page}페이지 크롤링 중...")

        go_to_page(driver, page)
        products = get_products(driver)

        new_count = 0
        for item in products:
            if item['상품코드'] not in seen_ids:
                total_results.append(item)
                seen_ids.add(item['상품코드'])
                new_count += 1

        if new_count == 0:
            print(f"🔚 더 이상 신규 상품 없음, 중단")
            break

    driver.quit()

    df = pd.DataFrame(total_results)
    df.to_csv("monitor_list.csv", index=False, encoding="utf-8-sig")
    print(f"✅ monitor_list.csv 저장 완료 - 총 {len(df)}개")

if __name__ == "__main__":
    url = "https://prod.danawa.com/list/?cate=112757"
    crawl_monitor_list_all(url)
