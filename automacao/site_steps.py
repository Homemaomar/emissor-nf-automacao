from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


class SiteStepsMixin:
    def esperar_visivel(self, by, locator, timeout=None):
        timeout = timeout or self.timeout
        return self.wait.until(
            EC.visibility_of_element_located((by, locator))
        )

    def esperar_clicavel(self, by, locator, timeout=None):
        timeout = timeout or self.timeout
        return self.wait.until(
            EC.element_to_be_clickable((by, locator))
        )

    def clicar(self, by, locator, timeout=None):
        elemento = self.esperar_clicavel(by, locator, timeout)
        elemento.click()
        return elemento

    def digitar(self, by, locator, valor, limpar=True, timeout=None):
        campo = self.esperar_visivel(by, locator, timeout)
        if limpar:
            campo.clear()
        campo.send_keys(str(valor))
        return campo

    def texto_presente(self, texto, timeout=None):
        timeout = timeout or self.timeout
        return self.wait.until(
            EC.presence_of_element_located((By.XPATH, f"//*[contains(normalize-space(), '{texto}')]"))
        )

    def elemento_existe(self, by, locator):
        try:
            self.driver.find_element(by, locator)
            return True
        except Exception:
            return False

    def obter_texto_se_existir(self, by, locator):
        try:
            return self.driver.find_element(by, locator).text.strip()
        except Exception:
            return ""