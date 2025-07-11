import pandas as pd
import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 스펙 기준 리스트
INCH_LIST = ["22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32",
             "34", "35", "37", "38", "39", "40", "42", "43", "45", "48", "49", "55", "57", "65"]
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

# 필터 함수
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

# 크롤링 함수
def crawl_specs_from_csv(input_csv="monitor_list.csv", output_csv="monitor_spec_list.csv"):
    df = pd.read_csv(input_csv)
    results = []

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')

    # Colab용 크롬 경로 (필요시 활성화)
    # options.binary_location = "/usr/bin/chromium-browser"

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 10)

    for idx, row in df.iterrows():
        product_id = str(row["상품코드"])
        model_name = row["모델명"]
        price = row["가격"]

        url = f"https://prod.danawa.com/info/?pcode={product_id}&cate=112757"
        print(f"🔍 [{idx+1}/{len(df)}] {model_name} → {url}")

        try:
            driver.get(url)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".spec_list")))
            time.sleep(1)

            spec_text = driver.find_element(By.CSS_SELECTOR, ".spec_list").text.strip()

            results.append({
                "상품코드": product_id,
                "모델명": model_name,
                "가격": price,
                "인치": extract_inch(spec_text),
                "해상도": extract_resolution(spec_text),
                "주사율": extract_refresh_rate(spec_text),
                "패널": extract_panel(spec_text)
            })

        except Exception as e:
            print(f"❌ 실패: {model_name} - {str(e)}")
            results.append({
                "상품코드": product_id,
                "모델명": model_name,
                "가격": price,
                "인치": "",
                "해상도": "",
                "주사율": "",
                "패널": ""
            })

    driver.quit()
    pd.DataFrame(results).to_csv(output_csv, index=False, encoding="utf-8-sig")
    print(f"✅ {output_csv} 저장 완료")

if __name__ == "__main__":
    crawl_specs_from_csv()
