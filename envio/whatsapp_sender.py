import os
import time
import urllib.parse
import ctypes

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class WhatsAppSender:
    def __init__(self, log_callback=None):
        self.log = log_callback or print
        self.driver = None

    # ==========================================
    # INICIAR WHATSAPP
    # ==========================================
    def iniciar(self):
        profile_path = r"C:\WhatsAppProfile"

        if not os.path.exists(profile_path):
            os.makedirs(profile_path)

        options = Options()
        options.add_argument(f"--user-data-dir={profile_path}")
        options.add_argument("--profile-directory=Default")
        options.add_argument("--disable-blink-features=AutomationControlled")

        self.driver = webdriver.Chrome(options=options)
        self.driver.get("https://web.whatsapp.com")

        self.log("Abrindo WhatsApp Web...")

        wait = WebDriverWait(self.driver, 120)

        try:
            wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']"))
            )
            self.log("WhatsApp ja esta logado.")
        except Exception:
            self.log("Escaneie o QR Code...")
            wait.until(EC.presence_of_element_located((By.XPATH, "//canvas")))
            wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']"))
            )
            self.log("WhatsApp conectado apos QR.")

    # ==========================================
    # ENVIAR MENSAGEM
    # ==========================================
    def enviar(self, numero, mensagem, timeout=30):
        if not self.driver:
            raise Exception("Driver nao iniciado. Chame iniciar() primeiro.")

        wait = WebDriverWait(self.driver, timeout)

        try:
            self.log("==============================")
            self.log("ENVIANDO MENSAGEM WHATSAPP")
            self.log("==============================")

            numero = str(numero).strip()
            numero = numero.split(".")[0]
            numero = "".join(filter(str.isdigit, numero))

            if len(numero) < 10:
                raise Exception(f"Numero invalido: {numero}")

            self.log(f"Numero: {numero}")

            mensagem_codificada = urllib.parse.quote(mensagem)
            url = f"https://web.whatsapp.com/send?phone=55{numero}&text={mensagem_codificada}"
            self.driver.get(url)

            campo = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[@contenteditable='true']")
                )
            )

            time.sleep(1)
            campo.send_keys(Keys.ENTER)

            self.log("Mensagem enviada.")
            time.sleep(1)
            return True

        except Exception as exc:
            self.log(f"Erro ao enviar mensagem: {exc}")
            return False

    def _abrir_menu_anexo(self, wait):
        botao_mais = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//span[@data-icon='plus-rounded']")
            )
        )
        botao_mais.click()

    def _clicar_documento(self, wait):
        botao_documento = wait.until(
            EC.presence_of_element_located((By.XPATH, "//span[text()='Documento']"))
        )
        self.driver.execute_script("arguments[0].click();", botao_documento)

    def _mapear_novo_input(self):
        return self.driver.find_elements(By.XPATH, "//input[@type='file']")

    def _fechar_dialogo_abrir_windows(self):
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW("#32770", "Abrir")
            if hwnd:
                user32.PostMessageW(hwnd, 0x0010, 0, 0)
                time.sleep(0.5)
        except Exception:
            pass

    # ==========================================
    # ENVIAR ARQUIVOS
    # ==========================================
    def enviar_multiplos_arquivos(self, caminhos_arquivos, timeout=40):
        wait = WebDriverWait(self.driver, timeout)

        try:
            self.log("Enviando arquivos em lote...")

            arquivos_validos = [c for c in caminhos_arquivos if os.path.exists(c)]
            if not arquivos_validos:
                raise Exception("Nenhum arquivo valido")

            for caminho_arquivo in arquivos_validos:
                self.log(f"Enviando: {caminho_arquivo}")

                inputs_antes = self._mapear_novo_input()
                self._abrir_menu_anexo(wait)
                self._clicar_documento(wait)
                time.sleep(1)

                inputs_depois = self._mapear_novo_input()
                novos_inputs = [inp for inp in inputs_depois if inp not in inputs_antes]

                if not novos_inputs:
                    raise Exception("Novo input de documento nao encontrado")

                input_file = novos_inputs[0]
                input_file.send_keys(caminho_arquivo)
                self._fechar_dialogo_abrir_windows()

                botao_enviar = wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//span[@data-icon='wds-ic-send-filled']")
                    )
                )
                botao_enviar.click()
                self._fechar_dialogo_abrir_windows()

                self.log(f"Arquivo enviado: {caminho_arquivo}")
                time.sleep(2)

            return True

        except Exception as exc:
            self.log(f"Erro no envio em lote: {exc}")
            return False

    # ==========================================
    # FINALIZAR
    # ==========================================
    def finalizar(self):
        try:
            self.log("Finalizando WhatsApp...")
            if self.driver:
                self.driver.quit()
        except Exception as exc:
            self.log(f"Erro ao finalizar: {exc}")

    def _dividir_em_lotes(self, lista, tamanho_lote=10):
        for i in range(0, len(lista), tamanho_lote):
            yield lista[i:i + tamanho_lote]
