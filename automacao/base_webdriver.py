import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


class BaseWebDriver:
    def __init__(
        self,
        logger,
        log_callback=None,
        headless=False,
        timeout=20,
        pasta_evidencias="logs/evidencias",
        driver_path=None
    ):
        self.logger = logger
        self.log_callback = log_callback
        self.headless = headless
        self.timeout = timeout
        self.pasta_evidencias = pasta_evidencias
        self.driver_path = driver_path

        Path(self.pasta_evidencias).mkdir(parents=True, exist_ok=True)

        self.driver = None
        self.wait = None

    def _log_callback(self, mensagem: str):
        if callable(self.log_callback):
            self.log_callback(mensagem)

    def iniciar_driver(self):
        if self.driver:
            return self.driver

        options = Options()

        if self.headless:
            options.add_argument("--headless=new")

        options.add_argument("--start-maximized")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--log-level=3")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-infobars")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        if self.driver_path:
            service = Service(self.driver_path)
            self.driver = webdriver.Chrome(service=service, options=options)
        else:
            self.driver = webdriver.Chrome(options=options)

        self.wait = WebDriverWait(self.driver, self.timeout)

        self.logger.info("WebDriver iniciado com sucesso.")
        self._log_callback("WebDriver iniciado com sucesso.")
        return self.driver

    def fechar_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None
                self.wait = None
                self.logger.info("WebDriver encerrado.")
                self._log_callback("WebDriver encerrado.")

    def _salvar_evidencias(self, etapa: str, tentativa: int):
        if not self.driver:
            return

        nome_base = f"{etapa.replace(' ', '_')}_tentativa_{tentativa}"
        caminho_png = os.path.join(self.pasta_evidencias, f"{nome_base}.png")
        caminho_html = os.path.join(self.pasta_evidencias, f"{nome_base}.html")

        self.driver.save_screenshot(caminho_png)

        with open(caminho_html, "w", encoding="utf-8") as f:
            f.write(self.driver.page_source)

        self.logger.info(f"Evidências salvas: {caminho_png} | {caminho_html}")

    def _tentar_recuperar_estado(self):
        try:
            if self.driver:
                self.driver.refresh()
                self.logger.info("Página atualizada para recuperação de estado.")
        except Exception as e:
            self.logger.error(f"Falha ao recuperar estado: {e}")