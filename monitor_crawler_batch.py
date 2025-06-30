from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from datetime import datetime
from pytz import timezone
import csv
import os
import traceback

# 설정
CHROMEDRIVER_PATH = 'chromedriver'
DATA_PATH = 'crawl_data'
TIMEZONE = 'Asia/Seoul'

CATEGORY_NAME = 'Monitor'
CATEGORY_URL = 'https://prod.danawa.com/list/?cate=112757'

class DanawaMonitorCrawler:
    def __init__(self):
        self.errorList = []
        self.chrome_option = webdriver.ChromeOptions()
        self.chrome_option.add_argument('--headless')
        self.chrome_option.add_argument('--window-size=1920,1080')
        self.chrome_option.add_argument('--disable-gpu')
        self.chrome_option.add_argument('lang=ko_KR')

    def GetCurrentDate(self):
        return datetime.now(timezone(TIMEZONE))

    def Crawl(self):
        print(f'Crawling Start: {CATEGORY_NAME}')
        seen_ids = set()
        all_data = []
        browser = None  # 브라우저 초기화

        try:
            browser = webdriver.Chrome(executable_path=CHROMEDRIVER_PATH, options=self.chrome_option)
            browser.implicitly_wait(5)
            browser.get(CATEGORY_URL)

            # 90개 보기 설정
            try:
                browser.find_element(By.XPATH, '//option[@value="90"]').click()
                WebDriverWait(browser, 10).until(
                    EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover'))
                )
            except:
                print("❌ 90개 보기 설정 실패")

            sort_methods = ["NEW", "BEST", "DATE", "LOW_PRICE"]
            for method in sort_methods:
                try:
                    tab = browser.find_element(By.XPATH, f'//li[@data-sort-method="{method}"]')
                    browser.execute_script("arguments[0].click();", tab)
                    WebDriverWait(browser, 10).until(
                        EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover'))
                    )
                except:
                    print(f"❌ 정렬 기준 {method} 클릭 실패")
                    continue

                while True:
                    try:
                        product_items = browser.find_elements(By.CSS_SELECTOR, 'ul.product_list > li')
                        for product in product_items:
                            pid = product.get_attribute('id')
                            if not pid or 'ad' in pid or 'prod_ad_item' in product.get_attribute('class'):
                                continue
                            pid = pid.replace("productItem", "")
                            if pid in seen_ids:
                                continue

                            name = product.find_element(By.CSS_SELECTOR, 'div.prod_info p.prod_name a').text.strip()
                            try:
                                price = product.find_element(By.CSS_SELECTOR, 'p.price_sect strong').text.strip().replace(",", "")
                            except:
                                price = "가격없음"

                            all_data.append([pid, name, price])
                            seen_ids.add(pid)
                    except Exception as e:
                        print(f"❗ 상품 파싱 오류: {e}")
                        continue

                    # 다음 페이지
                    try:
                        next_btn = browser.find_element(By.CSS_SELECTOR, 'a.edge_nav.nav_next')
                        if 'disable' in next_btn.get_attribute('class'):
                            break
                        browser.execute_script("arguments[0].click();", next_btn)
                        WebDriverWait(browser, 10).until(
                            EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover'))
                        )
                    except:
                        break

        except Exception:
            print(traceback.format_exc())
            self.errorList.append(CATEGORY_NAME)

        finally:
            if browser:
                browser.quit()

        # 저장
        os.makedirs(DATA_PATH, exist_ok=True)
        output_path = os.path.join(DATA_PATH, f'{CATEGORY_NAME}.csv')
        with open(output_path, 'w', newline='', encoding='utf8') as f:
            writer = csv.writer(f)
            writer.writerow([self.GetCurrentDate().strftime('%Y-%m-%d %H:%M:%S')])
            for row in all_data:
                writer.writerow(row)

        print(f'Crawling Finish: {CATEGORY_NAME} | 총 수집: {len(all_data)}개')

if __name__ == '__main__':
    crawler = DanawaMonitorCrawler()
    crawler.Crawl()
