from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time


def realizar_login(driver, inscricao, senha):
    inscricao = str(inscricao or "").strip()
    senha = str(senha or "").strip()

    if not inscricao or not senha:
        raise ValueError(
            "Credenciais da prefeitura nao configuradas. Atualize login e senha nas configuracoes antes de emitir."
        )

    wait = WebDriverWait(driver, 5)

    driver.get("https://www.nfse.gov.br/EmissorNacional/Login")

    # esperar campo CNPJ aparecer
    campo_cnpj = wait.until(
        EC.presence_of_element_located((By.ID, "Inscricao"))
    )

    campo_cnpj.clear()
    campo_cnpj.send_keys(inscricao)

    # campo senha
    campo_senha = driver.find_element(By.ID, "Senha")
    campo_senha.clear()
    campo_senha.send_keys(senha)

    # pequeno delay para JS do site
    time.sleep(2)

    # clicar no botão entrar
    botao = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")

    driver.execute_script("arguments[0].click();", botao)

    print("Login enviado...")

    # aguardar mudança de página
    time.sleep(10)
