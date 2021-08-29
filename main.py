import time
import sys
import requests
import os
import json
import pandas as pd
import threading
from queue import Queue

from bs4 import BeautifulSoup

# load selenium components
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# Options = Options()
# Options.headless = True

class Driver(object):

    def __init__(self, url):
        self.url = url
        self.driver = webdriver.Firefox()
        self.driver.get(url)
    
    def get_driver(self):
        return self.driver

    def close(self):
        self.driver.close()
    
    def refresh(self):
        self.driver.refresh()
    
    def __exit__(self):
        self.close()
        self.driver.quit()


class Strategy(object):

    def __init__(self, url, username, password):
        self._url = url
        self._username = username
        self._password = password
        self._driver = Driver(self._url).get_driver()
    
    def main(self):
        # waiting for the webpage loaded completely
        wait = WebDriverWait(self._driver, 20)

        # click popup alert if have
        popup = wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[5]/a")))
        if popup:
            popup.click()
        
        # sign in click
        signin = wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/header/nav/ul/li[3]/a")))
        if signin:
            signin.click()

        # login to the page
        user_login = UserLogin(self._driver, self._username, self._password)
        user_login.login()

        # wait for login successfully
        time.sleep(8)
        
        categories = [
            "{}men/".format(self._url),
            "{}woman/".format(self._url),
            "{}kids/".format(self._url)
        ]

        category_urls = {}

        # find all <li> sub menu
        li_elements = self._driver.find_elements_by_class_name("navUser-item")
        # find a href of each li elements
        for li_element in li_elements:
            a_tags = li_element.find_elements_by_tag_name('a')
            category = a_tags[0].get_attribute('href')
            if category in categories:
                category_urls[a_tags[0]] = a_tags[3:]
        
        # Iterate all product and each tab for each category
        self.iterate_each_tab(category_urls)
    
    def iterate_each_tab(self, category_urls):
        """
        Iterate by opening each tab for each category
        """
        list_group_category_urls = []
        for key,categories in category_urls.items():
            # Mouse over
            ActionChains(self._driver).move_to_element(key).perform()
            # Group of category urls
            list_group_category_urls.append([category.get_attribute('href') for category in categories])
        
        for group_category_urls in list_group_category_urls:
            for category in group_category_urls:
                print("DEBUG: Iterating the category {}".format(category))
                # Open the new tab
                ActionChains(self._driver).key_down(Keys.CONTROL).send_keys('t').key_up(Keys.CONTROL).perform()

                self._driver.get(category)

                # Iterate each_category to scarpe all products
                self.iterate_each_category(category)

                # Close the tab
                ActionChains(self._driver).key_down(Keys.CONTROL).send_keys('w').key_up(Keys.CONTROL).perform()

    
    def iterate_each_category(self, category):
        # sleep 3s to wait for mouse hover success
        time.sleep(3)

        # scroll the page with infinite loading to load all products
        self.scroll_load_all_page()
    
    def scroll_load_all_page(self):
        scroll_pause_time = 1
        # Get scroll height
        previous_height = self._driver.execute_script("return document.body.scrollHeight")
        while True:
            # Scroll down to bottom
            self._driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            # Wait to load page
            time.sleep(scroll_pause_time)

            # Calculate new scroll height and compare with last scroll height
            new_height = self._driver.execute_script("return document.body.scrollHeight")
            if new_height == previous_height:
                break
            previous_height = new_height
        
        # Get all product urls
        product_urls = self.get_all_products()

        # Multiprocess to request multi urls
        self.multithread_get_product(product_urls)


    def get_all_products(self):
        product_urls = []
        elements = self._driver.find_elements_by_class_name('js-first-time')
        for element in elements:
            #print(element.get_attribute('href'))
            # save to a list of url of each products 
            product_urls.append(element.get_attribute('href'))
        
        return product_urls
    
    def multithread_get_product(self, product_urls):
        # set up the queue to hold all urls
        q = Queue(maxsize=0)
        # use many threads
        num_threads = 10
        for i in range(len(product_urls)):
            q.put((i, product_urls[i]))
        
        for i in range(num_threads):
            print('Starting thread {}'.format(str(i)))
            worker = threading.Thread(target=self.get_product_info, args=(q,))
            worker.setDaemon(True)
            worker.start()
        
        # wait util queue finished
        q.join()
        print('All product completed')
        
    
    def get_product_info(self, q):
        while not q.empty():
            worker = q.get()
            product_url = worker[1]
            try:
                # share cookie signed in from selenium for requests
                s = self.share_cookie_for_requests()

                res = s.get(product_url)
                soup = BeautifulSoup(res.content, features='html.parser')
                #print(soup)
                # for Name
                styles = soup.findAll('h1', {'class': 'productView-title'})
                name = styles[0].text
                # for Style
                style = styles[0].text.split('-')[1].strip()
                # for Description
                product_details = soup.findAll('div', {'class': 'product-details-subcontainer'})
                descriptions = product_details[0].findAll('p')
                description = descriptions[1].text
                # for Size
                sizes = soup.findAll('label', {'class': 'form-option form-option-size'})
                data_sizes = []
                for size in sizes:
                    data_sizes.append(size['data-size-label'])
                data_sizes.sort()
                # for color
                colors = soup.findAll('span', {'class': 'form-option-variant form-option-variant--color'})
                data_colors = []
                for color in colors:
                    data_colors.append(color['title'])
                data_colors.sort()

                # for price
                spans = soup.findAll('span', {'class': 'price price--withoutTax price-section--minor'})
                try:
                    piece_price = spans[0].text
                except Exception as e:
                    piece_price = 'NaN'
                # for Dozen Price
                dozen_price = 0
                # for Case Qty
                case_qty = 0
                # for Case Price
                case_price = 0
                # for MSRP Price
                msrp_price = 0

                # for images
                # for Style Item Image URL (Front)
                images = soup.findAll('img', {'class': 'productView-image--default'})
                front = back = side = False
                data_images = []
                for img in images:
                    data_images.append(img['src'])
                data_images.sort()

                # match colors with images front and back
                color_images = {}
                for color in data_colors:
                    for img_url in data_images:
                        if ('{}__'.format(color) in img_url or '{}_BACK__'.format(color) in img_url) and color in img_url:
                            if color not in color_images:
                                color_images[color] = [img_url]
                            else:
                                color_images[color].append(img_url)
                print(json.dumps(color_images, indent=2))

                # Group and save to csv
                data = {}
                data['Style'] = []
                data['Name'] = []
                data['Description'] = []
                data['Size'] = []
                data['Color'] = []
                data['Piece Price'] = []
                data['Dozen Price'] = []
                data['Case Qty'] = []
                data['Case Price'] = []
                data['MSRP Price'] = []
                data['Style Item Image URL (Front)'] = []
                data['Style Item Image URL (Back)'] = []
                data['Style Item Image URL (Side)'] = []

                for key in color_images.keys():
                    for size in data_sizes:
                        data['Style'].append(style)
                        data['Name'].append(name)
                        data['Description'].append(description)
                        data['Size'].append(size)
                        data['Color'].append(key)
                        data['Piece Price'].append(piece_price)
                        data['Dozen Price'].append(dozen_price)
                        data['Case Qty'].append(case_qty)
                        data['Case Price'].append(case_price)
                        data['MSRP Price'].append(msrp_price)
                        try:
                            data['Style Item Image URL (Front)'].append(color_images[key][0])
                        except Exception:
                            data['Style Item Image URL (Front)'].append('')
                        try:
                            data['Style Item Image URL (Back)'].append(color_images[key][1])
                        except Exception:
                            data['Style Item Image URL (Back)'].append('')
                    
                        data['Style Item Image URL (Side)'].append('')
                    
                    # save to csv
                    csv_output_lock = threading.Lock()
                    with csv_output_lock:
                        df = pd.DataFrame(data)
                        if os.path.isfile('output.csv'):
                            df.to_csv('output.csv', index=False, header=False, mode='a')
                        else:
                            df.to_csv('output.csv', index=False)
            except Exception as e:
                print('Failed to get product {}'.format(product_url))
                pass
            q.task_done()
        return True
        
    
    def share_cookie_for_requests(self):
        s = requests.Session()
        for cookie in self._driver.get_cookies():
            s.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])
        
        return s

class UserLogin(object):

    def __init__(self, driver, username, password):
        self._driver = driver
        self._username = username
        self._password = password

    def login(self):
        """
        Login to web page
        """
        self._driver.find_element_by_id("login_email").send_keys(self._username)
        self._driver.find_element_by_id("login_pass").send_keys(self._password)
        button = self._driver.find_element_by_xpath("/html/body/div[3]/div[2]/div/div[1]/form[1]/div/div[1]/div[6]/button")
        #self._driver.find_element_by_id("")
        button.click()

if __name__ == '__main__':
    URL = "https://www.ascolour.com.au/"
    USERNAME = "drew@bornthready.com"
    PASSWORD = "Converge101!@"
    strategy = Strategy(url=URL, username=USERNAME, password=PASSWORD)
    strategy.main()
    # test("https://www.ascolour.com.au/mens-classic-tee-5026/")
