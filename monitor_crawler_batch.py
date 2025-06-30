# -*- coding: utf-8 -*-

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from datetime import datetime, timedelta
from pytz import timezone
import csv
import os
import shutil
import traceback
import time

from collections import OrderedDict

CRAWLING_DATA_CSV_FILE = 'CrawlingCategory.csv'
DATA_PATH = 'crawl_data'
DATA_REFRESH_PATH = f'{DATA_PATH}/Last_Data'
TIMEZONE = 'Asia/Seoul'

DATA_REMARK = '//'
DATA_ROW_DIVIDER = '_'
DATA_PRODUCT_DIVIDER = '|'

STR_NAME = 'name'
STR_URL = 'url'
STR_CRAWLING_PAGE_SIZE = 'crawlingPageSize'

class DanawaMonitorCrawler:
    def __init__(self):
        self.errorList = []
        self.crawlingCategory = []
        with open(CRAWLING_DATA_CSV_FILE, 'r', newline='') as file:
            for row in csv.reader(file, skipinitialspace=True):
                if not row[0].startswith(DATA_REMARK):
                    self.crawlingCategory.append({
                        STR_NAME: row[0],
                        STR_URL: row[1],
                        STR_CRAWLING_PAGE_SIZE: int(row[2])
                    })

    def start(self):
        self.refresh_data()
        for category in self.crawlingCategory:
            self.crawl(category)
        self.sort_data()

    def crawl(self, category):
        name = category[STR_NAME]
        url = category[STR_URL]
        page_size = category[STR_CRAWLING_PAGE_SIZE]

        print(f'Crawling Start: {name}')
        filename = f'{name}.csv'
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([self.now().strftime('%Y-%m-%d %H:%M:%S')])

            chrome_option = webdriver.ChromeOptions()
            chrome_option.add_argument('--headless')
            chrome_option.add_argument('--window-size=1920,1080')
            chrome_option.add_argument('--disable-gpu')
            chrome_option.add_argument('lang=ko_KR')

            service = Service(ChromeDriverManager().install())
            browser = webdriver.Chrome(service=service, options=chrome_option)
            browser.implicitly_wait(3)

            try:
                collected = OrderedDict()
                for sort_method in ['NEW', 'BEST']:
                    browser.get(url)
                    WebDriverWait(browser, 5).until(EC.presence_of_element_located((By.XPATH, f'//li[@data-sort-method="{sort_method}"]'))).click()
                    time.sleep(1)

                    for page in range(1, page_size + 1):
                        print(f"  Sort: {sort_method}, Page: {page}")
                        WebDriverWait(browser, 10).until(EC.presence_of_element_located((By.CLASS_NAME, 'product_list')))
                        products = browser.find_elements(By.XPATH, '//ul[@class="product_list"]/li')
                        for product in products:
                            pid = product.get_attribute('id')
                            if not pid or pid.startswith('ad') or 'prod_ad_item' in product.get_attribute('class'):
                                continue

                            productId = pid[11:]
                            if productId in collected:
                                continue

                            try:
                                productName = product.find_element(By.XPATH, './div/div[2]/p/a').text.strip()
                                productPrices = product.find_elements(By.XPATH, './div/div[3]/ul/li')
                                priceStr = ''

                                for priceBlock in productPrices:
                                    if 'top5_button' in priceBlock.get_attribute('class'):
                                        continue
                                    if priceStr:
                                        priceStr += DATA_PRODUCT_DIVIDER
                                    try:
                                        mall = priceBlock.find_element(By.XPATH, './a/div[1]').text.strip()
                                        if not mall:
                                            mall = priceBlock.find_element(By.XPATH, './a/div[1]/span[1]').text.strip()
                                        price = priceBlock.find_element(By.XPATH, './a/div[2]/em').text.strip()
                                        priceStr += f'{mall}{DATA_ROW_DIVIDER}{price}'
                                    except:
                                        continue

                                collected[productId] = (productName, priceStr)
                            except:
                                continue

                        # 다음 페이지 이동
                        try:
                            next_btn = browser.find_element(By.XPATH, '//a[@class="edge_nav nav_next"]')
                            if 'disable' in next_btn.get_attribute('class'):
                                break
                            next_btn.click()
                            time.sleep(1)
                        except:
                            break

                for pid, (name, prices) in collected.items():
                    writer.writerow([pid, name, prices])

            except Exception:
                print(f'Error - {name}')
                print(traceback.format_exc())
                self.errorList.append(name)
            finally:
                browser.quit()

        print(f'Crawling Finish: {name}')

    def sort_data(self):
        print('Data Sort\n')

        for category in self.crawlingCategory:
            name = category[STR_NAME]
            temp_path = f'{name}.csv'
            final_path = f'{DATA_PATH}/{name}.csv'

            if not os.path.exists(temp_path):
                continue

            with open(temp_path, 'r', encoding='utf-8') as f:
                rows = list(csv.reader(f))

            if not rows:
                continue

            if not os.path.exists(DATA_PATH):
                os.makedirs(DATA_PATH)

            if not os.path.exists(final_path):
                with open(final_path, 'w', encoding='utf-8') as f:
                    pass

            with open(final_path, 'r', encoding='utf-8') as f:
                data_rows = list(csv.reader(f))

            if not data_rows:
                data_rows.append(['Id', 'Name'])

            data_rows[0].append(rows[0][0])

            for row in rows[1:]:
                if not row[0].isdigit():
                    continue
                updated = False
                for data in data_rows:
                    if data[0] == row[0]:
                        data.append(row[2])
                        updated = True
                        break
                if not updated:
                    new_data = [row[0], row[1]] + ['0'] * (len(data_rows[0]) - 3) + [row[2]]
                    data_rows.append(new_data)

            for data in data_rows:
                while len(data) < len(data_rows[0]):
                    data.append('0')

            header = data_rows.pop(0)
            data_rows.sort(key=lambda x: x[1])
            data_rows.insert(0, header)

            with open(final_path, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerows(data_rows)

            os.remove(temp_path)

            list_path = 'monitor_list.csv'
            with open(list_path, 'w', newline='', encoding='utf-8') as listfile:
                writer = csv.writer(listfile)
                writer.writerow(['Id', 'Name', 'Price'])
                for row in data_rows[1:]:
                    latest_price = row[-1]
                    writer.writerow([row[0], row[1], latest_price])

    def refresh_data(self):
        today = self.now()
        if today.day != 1:
            return

        print('Data Refresh\n')

        if not os.path.exists(DATA_REFRESH_PATH):
            os.makedirs(DATA_REFRESH_PATH)

        prev_month = today - timedelta(days=1)
        archive_path = f'{DATA_REFRESH_PATH}/{prev_month.strftime("%Y-%m")}'
        if not os.path.exists(archive_path):
            os.makedirs(archive_path)

        for file in os.listdir(DATA_PATH):
            if file.endswith('.csv'):
                shutil.move(os.path.join(DATA_PATH, file), os.path.join(archive_path, file))

    def now(self):
        return datetime.now(timezone(TIMEZONE))

if __name__ == '__main__':
    crawler = DanawaMonitorCrawler()
    crawler.start()
