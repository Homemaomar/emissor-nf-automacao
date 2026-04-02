from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def abrir_emissao_completa(driver):

    wait = WebDriverWait(driver, 20)

    # clicar no menu "Nova NFS-e"
    menu_nova_nf = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "a.dropdown-toggle"))
    )

    driver.execute_script("arguments[0].click();", menu_nova_nf)

    # clicar em "Emissão completa"
    emissao_completa = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//a[@href='/EmissorNacional/DPS/Pessoas']"))
    )

    emissao_completa.click()

    print("Tela de emissão completa aberta.")