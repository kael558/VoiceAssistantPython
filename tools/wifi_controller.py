from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import os

def toggle_wifi():
    chrome_install = ChromeDriverManager().install()
    folder = os.path.dirname(chrome_install)
    chromedriver_path = os.path.join(folder, "chromedriver.exe")

    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service)

    # Navigate to Google
    driver.get("http://192.168.2.1")

    # Wait for the page to load
    driver.implicitly_wait(20)

    # clcik on manageWifi id
    manage_wifi = driver.find_element(By.ID, "manageWifi")
    manage_wifi.click()

    # Wait for 5 seconds
    driver.implicitly_wait(5)

    # enter the pass in id password
    password = driver.find_element(By.ID, "password")
    password.send_keys("NQS142336000280")
    password.send_keys(Keys.RETURN)

    driver.implicitly_wait(5)

    # Toggle masterToggle
    master_toggle = driver.find_element(By.ID, "masterToggle")
    master_toggle.click()

    driver.implicitly_wait(5)

    # Save by clicking formSave
    form_save = driver.find_element(By.ID, "formSave")
    form_save.click()

    driver.implicitly_wait(10)

    # Close the browser after some time
    time.sleep(5)  # Let the user actually see something!
    driver.quit()

    return "The wifi has been toggled."
