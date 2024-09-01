from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def toggle_wifi():
    #s = Service('/usr/bin/chromedriver')
    s = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=s)

    try:
        # Navigate to Wifi Router
        driver.get("http://192.168.2.1")

        # Wait for the page to load and click on manageWifi
        wait = WebDriverWait(driver, 20)
        manage_wifi = wait.until(EC.element_to_be_clickable((By.ID, "manageWifi")))
        manage_wifi.click()

        # Wait for the password field to be present and enter the pass
        password = wait.until(EC.presence_of_element_located((By.ID, "password")))
        password.send_keys("NQS142336000280")
        password.send_keys(Keys.RETURN)

        # Wait for the masterToggle to be clickable and toggle it
        master_toggle = wait.until(EC.element_to_be_clickable((By.ID, "masterToggle")))
        master_toggle.click()

        # Wait for formSave to be clickable and click it
        form_save = wait.until(EC.element_to_be_clickable((By.ID, "formSave")))
        form_save.click()

        # Optionally wait for some time to ensure changes are applied
        time.sleep(5)  # Let the user actually see something!

    finally:
        # Ensure browser closes even if there is an error
        driver.quit()

    return "The wifi has been toggled."
