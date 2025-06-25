import time
import re
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# -------- 필터 기준 목록 -------- #
INCH_LIST = [
    "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32",
    "34", "35", "37", "38", "39", "40", "42", "43", "45", "48", "49", "55", "57", "65"
]
INCH_PATTERN = re.compile(rf"({'|'.join(INCH_LIST)})인치")

PANEL_LIST = ["OLED", "Nano-IPS", "IPS", "VA", "TN"]

RESOLUTION_LIST = [
    "1920 x 1080(FHD)", "1920 x 1200(WUXGA)", "1920 x 1280", "2048 x 1152", "2160 x 1440", "2240 x 1400",
    "2560 x 1080(WFHD)", "2560 x 1440(QHD)", "2560 x 1600(WQXGA)", "2560 x 2880(SDQHD)",
    "3440 x 1440(Ultra WQHD)", "3840 x 1080(DFHD)", "3840 x 1600(WQHD+)", "3840 x 2160(4K UHD)",
    "3840 x 2400(WQUXGA)", "3840 x 2560", "4096 x 2160(4K DCI)", "4200 x 2800",
    "5120 x 1440(DQHD)", "5120 x 2160(WUHD)", "5120 x 2880(5K UHD)"
]

REFRESH_RATE_LIST = [
    "60Hz", "65Hz", "70Hz", "75Hz", "90Hz", "95Hz", "100Hz", "120Hz", "138Hz", "144Hz",
    "155Hz", "160Hz", "165Hz", "170Hz", "175Hz", "180Hz", "200Hz", "220Hz", "240Hz",
    "250Hz", "260Hz", "270Hz", "280Hz", "300Hz", "320Hz", "360Hz", "380Hz", "400Hz",
    "480Hz", "500Hz", "540Hz"
]

def extract_inch(text):
    match = INCH_PATTERN.search(text)
    return match.group(0) if match else ""

def extract_panel(text):
    for panel in PANEL_LIST:
        if panel in text:
            return panel
    return ""

def extract_resolution(text):
    for res in RESOLUTION_LIST:
        if res in text:
            return res
    return ""

def extract_refresh_rate(text):
    for hz in REFRESH_RATE_LIST:
        if hz in text:
            return hz
    return ""

# -------- 메인 크롤링 함수 -------- #
def crawl_monitor_list(crawling_url, max_page=3):
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 10)

    driver.get(crawling_url)
    time.sleep(2)

    driver.find_element(By.XPATH, '//option[@value="90"]').click()
    wait.until(EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover')))

    results = []

    for i in range(1, max_page + 1):
        print(f"📄 {i}페이지 상품 크롤링 중...")
        wait.until(EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover')))
        time.sleep(1)

        products = driver.find_elements(By.XPATH, '//ul[@class="product_list"]/li')

        for product in products:
            try:
                if not product.get_attribute("id") or "ad" in product.get_attribute("id"):
                    continue
                product_id = product.get_attribute("id").replace("productItem", "")
                model_name = product.find_element(By.XPATH, './div/div[2]/p/a').text.strip()

                # 가격
                price = "가격없음"
                try:
                    price = product.find_element(By.CSS_SELECTOR, 'p.price_sect strong').text.replace(",", "").strip()
                except:
                    try:
                        price = product.find_element(By.CSS_SELECTOR, 'ul > li.mall_list_item > a > p.price_sect > strong').text.replace(",", "").strip()
                    except:
                        pass

                # 상세페이지 이동 후 스펙 추출
                detail_url = f"https://prod.danawa.com/info/?pcode={product_id}&cate=112757"
                driver.execute_script("window.open(arguments[0]);", detail_url)
                driver.switch_to.window(driver.window_handles[-1])
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'table.product_detail_table')))
                time.sleep(1)

                # 스펙 테이블
                spec_rows = driver.find_elements(By.CSS_SELECTOR, 'table.product_detail_table tr')
                raw_spec_text = " ".join([
                    f"{tr.find_element(By.TAG_NAME, 'th').text.strip()} {tr.find_element(By.TAG_NAME, 'td').text.strip()}"
                    for tr in spec_rows if tr.text
                ])

                inch = extract_inch(raw_spec_text)
                panel = extract_panel(raw_spec_text)
                resolution = extract_resolution(raw_spec_text)
                refresh = extract_refresh_rate(raw_spec_text)

                results.append({
                    "상품코드": product_id,
                    "모델명": model_name,
                    "가격": price,
                    "인치": inch,
                    "해상도": resolution,
                    "주사율": refresh,
                    "패널": panel
                })

                driver.close()
                driver.switch_to.window(driver.window_handles[0])

            except Exception as e:
                print(f"❌ 오류 발생: {e}")
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                continue

        try:
            if i % 10 == 0:
                driver.find_element(By.XPATH, '//a[@class="edge_nav nav_next"]').click()
            else:
                driver.find_element(By.XPATH, f'//a[@class="num "][{i%10}]').click()
        except:
            print("🔚 다음 페이지 없음")
            break

    driver.quit()

    df = pd.DataFrame(results)
    df.to_csv("monitor_spec_list.csv", index=False, encoding="utf-8-sig")
    print("✅ monitor_spec_list.csv 저장 완료")

if __name__ == "__main__":
    url = "https://prod.danawa.com/list/?cate=112757"
    crawl_monitor_list(url, max_page=3)