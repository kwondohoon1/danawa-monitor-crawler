import os
import csv
import time
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 설정값
DATA_FILE = 'monitor_price_list.csv'
TARGET_URL = 'https://prod.danawa.com/list/?cate=112757'
TODAY = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 크롬 드라이버 옵션 설정
options = Options()
options.add_argument('--headless')
options.add_argument('--disable-gpu')
options.add_argument('--no-sandbox')
options.add_argument('--window-size=1920,1080')

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 10)

# 상품 ID, 모델명, 가격 수집
def collect_monitor_data():
    driver.get(TARGET_URL)
    time.sleep(2)

    driver.find_element(By.XPATH, '//option[@value="90"]').click()
    time.sleep(1)

    product_map = {}
    visited_ids = set()
    tab_keys = ["BEST", "NEW"]

    for tab in tab_keys:
        try:
            driver.find_element(By.XPATH, f'//li[@data-sort-method="{tab}"]').click()
            time.sleep(2)
        except:
            continue

        for page in range(1, 15):  # 최대 14페이지까지 반복
            print(f"🔍 {tab}탭 - {page}페이지 수집 중...")
            time.sleep(1)
            products = driver.find_elements(By.XPATH, '//ul[@class="product_list"]/li')

            for product in products:
                pid = product.get_attribute("id")
                if not pid or "ad" in pid or not pid.startswith("productItem"):
                    continue
                pid = pid.replace("productItem", "")
                if pid in visited_ids:
                    continue

                try:
                    name = product.find_element(By.XPATH, './div/div[2]/p/a').text.strip()
                    price = product.find_element(By.CSS_SELECTOR, 'p.price_sect strong').text.replace(",", "").strip()
                    visited_ids.add(pid)
                    product_map[pid] = {"Name": name, "Price": price}
                except:
                    continue

            try:
                if page % 10 == 0:
                    driver.find_element(By.CSS_SELECTOR, 'a.edge_nav.nav_next').click()
                else:
                    driver.find_element(By.XPATH, f'//a[@class="num "][text()="{(page%10)+1}"]').click()
            except:
                break

    return product_map

# CSV 파일 업데이트
def update_csv(product_map):
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
    else:
        df = pd.DataFrame(columns=["Id", "Name"])

    if TODAY not in df.columns:
        df[TODAY] = 0

    existing_ids = set(df["Id"].astype(str))
    for pid, info in product_map.items():
        if pid in existing_ids:
            df.loc[df["Id"] == pid, TODAY] = info["Price"]
        else:
            new_row = {"Id": pid, "Name": info["Name"], TODAY: info["Price"]}
            for col in df.columns:
                if col not in new_row:
                    new_row[col] = 0
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    df = df.sort_values(by="Name")
    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
    print(f"✅ {DATA_FILE} 저장 완료")

# 실행
if __name__ == "__main__":
    print("🚀 모니터 가격 수집 시작")
    result = collect_monitor_data()
    driver.quit()
    update_csv(result)
