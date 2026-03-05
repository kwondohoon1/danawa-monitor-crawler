import pandas as pd
import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# -----------------------------
# 다나와 맞춤형 필터 함수 (슬래시 분리 및 정규식 활용)
# -----------------------------
def extract_inch(text):
    """ '34인치' 형태에서 숫자+인치만 정확히 추출 """
    match = re.search(r'(\d+)\s*인치', text)
    return match.group(0).replace(" ", "") if match else ""

def extract_resolution(text):
    """ '숫자 x 숫자' 패턴이 포함된 슬래시(/) 덩어리를 통째로 추출 (예: Ultra WQHD(3440 x 1440)) """
    for part in text.split('/'):
        if re.search(r'\d{3,4}\s*[xX]\s*\d{3,4}', part):
            return part.strip()
    return ""

def extract_refresh_rate(text):
    """ 텍스트 내에서 가장 높은 Hz 숫자를 찾아서 반환 (165Hz가 65Hz로 오인식되는 것 방지) """
    hz_list = re.findall(r'(\d+)\s*Hz', text, re.IGNORECASE)
    if hz_list:
        max_hz = max(map(int, hz_list))
        return f"{max_hz}Hz"
    return ""

def extract_panel(text):
    """ 주요 패널 키워드가 포함된 슬래시(/) 덩어리를 통째로 추출 (예: IPS Black, Nano-IPS) """
    panel_keywords = ["OLED", "IPS", "VA", "TN"]
    for part in text.split('/'):
        for keyword in panel_keywords:
            if keyword in part.upper():
                return part.strip()
    return ""

# -----------------------------
# 크롤링 메인 로직
# -----------------------------
def crawl_specs_from_csv(input_csv="monitor_list.csv", output_csv="monitor_spec_list.csv"):
    df = pd.read_csv(input_csv)
    results = []

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')

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
