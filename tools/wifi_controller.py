from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from selenium.webdriver.chrome.options import Options

def toggle_wifi():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')

    s = Service('/usr/lib/chromium-browser/chromedriver')
    driver = webdriver.Chrome(service=s, options=chrome_options)

    driver.get("http://192.168.2.1")

    wait = WebDriverWait(driver, 60)

    # Wait and click on "Manage Wifi"
    manage_wifi = wait.until(EC.element_to_be_clickable((By.ID, "manageWifi")))
    manage_wifi.click()

    # Wait for password input to appear and send the password
    password = wait.until(EC.visibility_of_element_located((By.ID, "password")))
    password.send_keys("NQS142336000280")
    password.send_keys(Keys.RETURN)

    # Wait for master toggle to become clickable and click it
    master_toggle = wait.until(EC.element_to_be_clickable((By.ID, "masterToggle")))
    master_toggle.click()

    # Wait for save button to be clickable and click it
    form_save = wait.until(EC.element_to_be_clickable((By.ID, "formSave")))
    form_save.click()

    # Optional: wait for any confirmation or completion message, if available
    time.sleep(10)  # Delay for router to apply changes if needed

    driver.quit()
    return "The wifi has been toggled."

if __name__ == "__main__":
    toggle_wifi()

