# -*- coding: utf-8 -*-

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from datetime import datetime, timedelta
from pytz import timezone
import csv
import os
import os.path
import shutil
import traceback

from multiprocessing import Pool

# 설정
PROCESS_COUNT = 1  # 모니터만 수집하므로 1로 설정
CRAWLING_DATA_CSV_FILE = 'CrawlingCategory.csv'
DATA_PATH = 'crawl_data'
DATA_REFRESH_PATH = f'{DATA_PATH}/Last_Data'
CHROMEDRIVER_PATH = 'chromedriver'
TIMEZONE = 'Asia/Seoul'

# 구분자
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
        self.start_crawling()
        self.sort_data()

    def start_crawling(self):
        chrome_option = webdriver.ChromeOptions()
        chrome_option.add_argument('--headless')
        chrome_option.add_argument('--window-size=1920,1080')
        chrome_option.add_argument('--disable-gpu')
        chrome_option.add_argument('lang=ko_KR')

        pool = Pool(processes=PROCESS_COUNT)
        pool.map(self.crawl_category, self.crawlingCategory)
        pool.close()
        pool.join()

    def crawl_category(self, categoryValue):
        name = categoryValue[STR_NAME]
        url = categoryValue[STR_URL]
        page_size = categoryValue[STR_CRAWLING_PAGE_SIZE]

        print(f'Crawling Start: {name}')
        filename = f'{name}.csv'
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([self.now().strftime('%Y-%m-%d %H:%M:%S')])

            try:
                browser = webdriver.Chrome(CHROMEDRIVER_PATH, options=webdriver.ChromeOptions())
                browser.get(url)
                WebDriverWait(browser, 5).until(
                    EC.element_to_be_clickable((By.XPATH, '//option[@value="90"]'))
                ).click()
                WebDriverWait(browser, 10).until(
                    EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover'))
                )

                for i in range(-1, page_size):
                    if i == -1:
                        browser.find_element(By.XPATH, '//li[@data-sort-method="NEW"]').click()
                    elif i == 0:
                        browser.find_element(By.XPATH, '//li[@data-sort-method="BEST"]').click()
                    elif i > 0:
                        if i % 10 == 0:
                            browser.find_element(By.CLASS_NAME, 'edge_nav.nav_next').click()
                        else:
                            browser.find_element(By.XPATH, f'//a[@class="num "][{i % 10}]').click()

                    WebDriverWait(browser, 10).until(
                        EC.invisibility_of_element((By.CLASS_NAME, 'product_list_cover'))
                    )

                    products = browser.find_elements(By.XPATH, '//ul[@class="product_list"]/li')
                    for product in products:
                        pid = product.get_attribute('id')
                        if not pid or pid.startswith('ad') or 'prod_ad_item' in product.get_attribute('class'):
                            continue

                        productId = pid[11:]
                        productName = product.find_element(By.XPATH, './div/div[2]/p/a').text.strip()
                        productPrices = product.find_elements(By.XPATH, './div/div[3]/ul/li')
                        priceStr = ''

                        isMall = 'prod_top5' in product.find_element(By.XPATH, './div/div[3]').get_attribute('class')

                        for priceBlock in productPrices:
                            if 'top5_button' in priceBlock.get_attribute('class'):
                                continue

                            if priceStr:
                                priceStr += DATA_PRODUCT_DIVIDER

                            if isMall:
                                mallName = priceBlock.find_element(By.XPATH, './a/div[1]').text.strip()
                                if not mallName:
                                    mallName = priceBlock.find_element(By.XPATH, './a/div[1]/span[1]').text.strip()
                                price = priceBlock.find_element(By.XPATH, './a/div[2]/em').text.strip()
                                priceStr += f'{mallName}{DATA_ROW_DIVIDER}{price}'
                            else:
                                desc = priceBlock.find_element(By.XPATH, './div/p').text.strip()
                                desc = self.remove_rank(desc.replace('\n', DATA_ROW_DIVIDER))
                                price = priceBlock.find_element(By.XPATH, './p[2]/a/strong').text.strip()
                                priceStr += f'{desc}{DATA_ROW_DIVIDER}{price}' if desc else price

                        writer.writerow([productId, productName, priceStr])

                browser.quit()

            except Exception:
                print(f'Error - {name}')
                print(traceback.format_exc())
                self.errorList.append(name)

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

            data_rows[0].append(rows[0][0])  # 날짜

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

    def remove_rank(self, text):
        if len(text) >= 2 and text[0].isdigit() and text[1] == '위':
            return text[2:].strip()
        return text


if __name__ == '__main__':
    crawler = DanawaMonitorCrawler()
    crawler.start()
