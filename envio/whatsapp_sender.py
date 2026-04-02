import time
import os
import urllib.parse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options


class WhatsAppSender:

    def __init__(self, log_callback=None):
        self.log = log_callback or print
        self.driver = None

    # ==========================================
    # INICIAR WHATSAPP
    # ==========================================
    def iniciar(self):

        options = Options()
        options.add_argument(r"--user-data-dir=C:\AutomaçãoNotaFiscal\chrome_profile")

        self.driver = webdriver.Chrome(options=options)
        self.driver.get("https://web.whatsapp.com")

        self.log("📱 Inicializando WhatsApp Web...")

        wait = WebDriverWait(self.driver, 60)

        try:
            wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']"))
            )
            self.log("✅ WhatsApp conectado automaticamente!")

        except:
            self.log("⚠️ Escaneie o QR Code...")

            wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']"))
            )

            self.log("✅ WhatsApp conectado!")

    # ==========================================
    # ENVIAR MENSAGEM (ABRE CONVERSA)
    # ==========================================
    def enviar(self, numero, mensagem, timeout=30):

        if not self.driver:
            raise Exception("Driver não iniciado. Chame iniciar() primeiro.")

        wait = WebDriverWait(self.driver, timeout)

        try:
            self.log("\n==============================")
            self.log("📤 ENVIANDO MENSAGEM WHATSAPP")
            self.log("==============================")

            # NORMALIZAR NÚMERO
            numero = str(numero).strip()
            numero = numero.split(".")[0]
            numero = ''.join(filter(str.isdigit, numero))

            if len(numero) < 10:
                raise Exception(f"Número inválido: {numero}")

            self.log(f"📞 Número: {numero}")

            # ENCODE DA MENSAGEM
            mensagem_codificada = urllib.parse.quote(mensagem)

            # ABRIR CONVERSA
            url = f"https://web.whatsapp.com/send?phone=55{numero}&text={mensagem_codificada}"
            self.driver.get(url)

            # AGUARDAR CAMPO
            campo = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[@contenteditable='true']")
                )
            )

            time.sleep(1)

            # ENVIAR MENSAGEM
            campo.send_keys(Keys.ENTER)

            self.log("✅ Mensagem enviada!")

            time.sleep(1)

            return True

        except Exception as e:
            self.log(f"❌ Erro ao enviar mensagem: {e}")
            return False

    # ==========================================
    # ENVIAR ARQUIVO (NA CONVERSA ABERTA)
    # ==========================================
    def enviar_arquivo(self, caminho_arquivo, timeout=40):

        wait = WebDriverWait(self.driver, timeout)

        try:
            self.log("📎 Enviando arquivo...")

            if not os.path.exists(caminho_arquivo):
                raise Exception(f"Arquivo não encontrado: {caminho_arquivo}")

            # =========================
            # 1. MAPEAR INPUTS ANTES
            # =========================
            inputs_antes = self.driver.find_elements(By.XPATH, "//input[@type='file']")
            self.log(f"🔍 Inputs antes: {len(inputs_antes)}")

            # =========================
            # 2. CLICAR NO "+"
            # =========================
            botao_mais = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//span[@data-icon='plus-rounded']")
                )
            )
            botao_mais.click()

            # =========================
            # 3. CLICAR EM DOCUMENTO (JS pra evitar travamento)
            # =========================
            botao_documento = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//span[text()='Documento']")
                )
            )

            self.driver.execute_script("arguments[0].click();", botao_documento)

            time.sleep(1)

            # =========================
            # 4. MAPEAR INPUTS DEPOIS
            # =========================
            inputs_depois = self.driver.find_elements(By.XPATH, "//input[@type='file']")
            self.log(f"🔍 Inputs depois: {len(inputs_depois)}")

            # =========================
            # 5. IDENTIFICAR NOVO INPUT
            # =========================
            novos_inputs = [i for i in inputs_depois if i not in inputs_antes]

            if not novos_inputs:
                raise Exception("❌ Novo input não encontrado")

            input_file = novos_inputs[0]

            # =========================
            # 6. LOG DETALHADO DOS INPUTS
            # =========================
            for i, inp in enumerate(inputs_depois):
                try:
                    accept = inp.get_attribute("accept")
                    visible = inp.is_displayed()
                    self.log(f"Input {i} → accept: {accept} | visível: {visible}")
                except:
                    self.log(f"Input {i} → erro ao inspecionar")

            self.log(f"✅ INPUT ESCOLHIDO: index {inputs_depois.index(input_file)}")

            # =========================
            # 7. ENVIAR ARQUIVO
            # =========================
            self.log(f"📤 Upload: {caminho_arquivo}")
            input_file.send_keys(caminho_arquivo)

            # =========================
            # 8. AGUARDAR BOTÃO ENVIAR
            # =========================
            botao_enviar = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//span[@data-icon='wds-ic-send-filled']")
                )
            )

            botao_enviar.click()

            self.log("📨 Arquivo enviado com sucesso!")

            # =========================
            # 9. FECHAR POSSÍVEL POPUP WINDOWS
            # =========================
            try:
                import pyautogui
                time.sleep(1)
                pyautogui.press("esc")
            except:
                pass

            return True

        except Exception as e:
            self.log(f"❌ Erro ao enviar arquivo: {e}")
            return False

    # ==========================================
    # FINALIZAR
    # ==========================================
    def finalizar(self):
        try:
            self.log("🔚 Finalizando WhatsApp...")
            if self.driver:
                self.driver.quit()
        except Exception as e:
            self.log(f"Erro ao finalizar: {e}")