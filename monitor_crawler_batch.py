import pandas as pd
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

def crawl_monitor_list():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("lang=ko_KR")

    driver = webdriver.Chrome(options=options)
    base_url = "https://prod.danawa.com/list/?cate=112758"

    results = []
    page = 1

    while True:
        url = f"{base_url}&page={page}"
        print(f"🔍 크롤링 중: {url}")
        driver.get(url)
        time.sleep(2)

        product_list = driver.find_elements(By.CSS_SELECTOR, "ul.product_list li.prod_item")
        if not product_list:
            break

        new_items = 0
        for product in product_list:
            try:
                if not product.get_attribute('id') or 'ad' in product.get_attribute('id'):
                    continue

                model_name = product.find_element(By.CSS_SELECTOR, "p.prod_name a").text.strip()
                product_id = product.get_attribute("id").replace("productItem", "").strip()
                try:
                    price = product.find_element(By.CSS_SELECTOR, "p.price_sect strong").text.replace(",", "").strip()
                except:
                    price = "가격없음"

                results.append({
                    "상품코드": product_id,
                    "모델명": model_name,
                    "가격": price
                })
                new_items += 1
            except:
                continue

        if new_items == 0:
            break
        page += 1

    driver.quit()
    df = pd.DataFrame(results)
    df.to_csv("monitor_list.csv", index=False, encoding='utf-8-sig')
    print("✅ monitor_list.csv 저장 완료")

if __name__ == "__main__":
    crawl_monitor_list()