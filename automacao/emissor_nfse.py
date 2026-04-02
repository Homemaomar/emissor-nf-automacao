print("🔥 INICIO emissor_nfse")
import os
import time
import shutil

from pathlib import Path
from datetime import datetime
from selenium.webdriver.common.by import By
from automacao.login import realizar_login
from automacao.base_webdriver import BaseWebDriver
from automacao.site_steps import SiteStepsMixin
from automacao.decorators import etapa_automacao
from automacao.excecoes import (
    AutomacaoErro,
    NotaJaEmitidaErro,
    EmissaoNaoAutorizadaErro,
)

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait


print("BaseWebDriver:", BaseWebDriver)
print("SiteStepsMixin:", SiteStepsMixin)
print("🔥 ANTES DA CLASSE")

class EmissorNFSe(BaseWebDriver, SiteStepsMixin):

    def __init__(
        self,
        logger,
        log_callback=None,
        input_callback=None,
        headless=False,
        timeout=20,
        pasta_evidencias="logs/evidencias",
        driver_path=None,
        caminho_base=None,                 # 📥 EXCEL (.xlsm)
        pasta_saida_base=r"C:\Notas"       # 📤 SAÍDA
    ):
        super().__init__(
            logger=logger,
            log_callback=log_callback,
            headless=headless,
            timeout=timeout,
            pasta_evidencias=pasta_evidencias,
            driver_path=driver_path
        )

        import os

        # ===============================
        # 🔥 DEFINIR PRIMEIRO (ESSENCIAL)
        # ===============================
        self.caminho_base = caminho_base
        self.pasta_saida_base = pasta_saida_base

        # ===============================
        # CALLBACKS
        # ===============================
        self.input_callback = input_callback

        # ===============================
        # 📥 ENTRADA (PLANILHA)
        # ===============================
        if not self.caminho_base:
            raise ValueError("❌ caminho_base não foi informado!")

        if not os.path.isfile(self.caminho_base):
            raise ValueError(
                f"❌ caminho_base precisa ser um ARQUIVO válido (.xlsm)\n➡️ Recebido: {self.caminho_base}"
            )

        # ===============================
        # 📤 SAÍDA (ARQUIVOS)
        # ===============================
        if not self.pasta_saida_base:
            raise ValueError("❌ pasta_saida_base não foi informada!")

        if not os.path.exists(self.pasta_saida_base):
            os.makedirs(self.pasta_saida_base, exist_ok=True)

        if not os.path.isdir(self.pasta_saida_base):
            raise ValueError(
                f"❌ pasta_saida_base precisa ser uma PASTA válida\n➡️ Recebido: {self.pasta_saida_base}"
            )

        # ===============================
        # 🧪 MODO TESTE
        # ===============================
        self.modo_teste = True

        # ===============================
        # 📁 PASTA TEMP
        # ===============================
        self.pasta_temp = os.path.join(self.pasta_saida_base, "_temp")
        os.makedirs(self.pasta_temp, exist_ok=True)

        # ===============================
        # DEBUG
        # ===============================
        if self.log_callback:
            self.log_callback("========== CONFIGURAÇÃO INICIAL ==========")
            self.log_callback(f"📂 Planilha (entrada): {self.caminho_base}")
            self.log_callback(f"📁 Pasta saída: {self.pasta_saida_base}")
            self.log_callback(f"🧪 Pasta temporária: {self.pasta_temp}")
            self.log_callback(f"📄 É arquivo? {os.path.isfile(self.caminho_base)}")
            self.log_callback(f"📁 É pasta saída? {os.path.isdir(self.pasta_saida_base)}")
        
    def _log(self, msg):
        print(msg)

        if hasattr(self, "logger") and self.logger:
            self.logger.info(msg)

        if hasattr(self, "log_callback") and callable(self.log_callback):
            self.log_callback(msg)
    def limpar_descricao(self, descricao):

        if not descricao:
                return ""

        texto = descricao.upper()

        # corta tudo a partir de PERÍODO
        if "PERÍODO" in texto:
            texto = texto.split("PERÍODO")[0]

        return texto.strip()
    # ABRIR PORTAL
    @etapa_automacao("Abrir Portal", tentativas=3, espera_segundos=2)
    def abrir_portal(self):
        url = "https://www.nfse.gov.br/EmissorNacional/Login"
        self.driver.get(url)
    # LOGIN (UMA VEZ)
    @etapa_automacao("Login", tentativas=2, espera_segundos=2)
    def preparar_sessao(self):

        self._log("🌐 Abrindo navegador...")

        self.iniciar_driver()

        self._log("🌐 Acessando portal...")

        self.abrir_portal()

        self._log("🔐 Realizando login...")

        realizar_login(self.driver)

        self._log("✅ Login realizado com sucesso")
    # ACESSAR EMISSÃO
    @etapa_automacao("Acessar Tela de Emissão", tentativas=3, espera_segundos=2)
    def acessar_tela_emissao(self):

        self._log("📂 Acessando menu Nova NFS-e...")

        wait = self.wait
        driver = self.driver

        menu = wait.until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//li[contains(@class,'dropdown')]//a[contains(@class,'dropdown-toggle')]"
            ))
        )

        menu.click()

        emissao = wait.until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//a[contains(@href, '/DPS/Pessoas')]"
            ))
        )

        emissao.click()

        wait.until(
            EC.presence_of_element_located((By.ID, "DataCompetencia"))
        )

        self._log("✅ Tela de emissão carregada")
    def esperar_loading_sumir(self):
        try:
            self.wait.until(
                EC.invisibility_of_element_located((By.ID, "modalLoading"))
            )

            # 🔥 garante que realmente sumiu visualmente
            time.sleep(1)

        except:
            pass
    def esperar_elemento_livre(self, elemento):
        try:
            self.wait.until(lambda d: elemento.is_displayed() and elemento.is_enabled())
        except:
            pass
    @etapa_automacao("Página 1", tentativas=3, espera_segundos=2)
    def preencher_pagina_1(self, dados_nota: dict):

        self._log("🧾 Preenchendo Página 1...")

        wait = self.wait
        driver = self.driver

        campo_data = wait.until(
            EC.presence_of_element_located((By.ID, "DataCompetencia"))
        )

        campo_data.clear()

        data_hoje = datetime.today().strftime("%d/%m/%Y")

        campo_data.send_keys(data_hoje)
        campo_data.send_keys(Keys.TAB)

        self.esperar_loading_sumir()

        radio_brasil = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//label[contains(.,'Brasil')]"))
        )

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            radio_brasil
        )

        self.esperar_loading_sumir()
        self.esperar_elemento_livre(radio_brasil)

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", radio_brasil)
        time.sleep(0.5)

        driver.execute_script("arguments[0].click();", radio_brasil)

        campo_cnpj = wait.until(
            EC.visibility_of_element_located((By.ID, "Tomador_Inscricao"))
        )

        campo_cnpj.clear()
        campo_cnpj.send_keys(dados_nota["cnpj"])
        campo_cnpj.send_keys(Keys.TAB)

        self.esperar_loading_sumir()

        # BOTÃO AVANÇAR
        botao_avancar = wait.until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(.,'Avançar')]"))
        )

        self._log("🔎 Preparando botão Avançar...")

        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            botao_avancar
        )

        time.sleep(1)

        self.esperar_loading_sumir()

        botao_avancar = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Avançar')]"))
        )

        try:
            botao_avancar.click()
        except Exception:
            self._log("⚠ Clique interceptado, usando JavaScript...")
            driver.execute_script("arguments[0].click();", botao_avancar)

        self._log("➡️ Página 1 concluída")
    # PÁGINA 2
    @etapa_automacao("Página 2", tentativas=3, espera_segundos=2)
    def preencher_pagina_2(self, dados_nota: dict):

        print("📄 Preenchendo Página 2...")
        print(f"📦 DADOS RECEBIDOS: {dados_nota}")
        
        wait = self.wait
        driver = self.driver

        # ==========================
        # AGUARDAR CARREGAMENTO
        # ==========================
        wait.until(
            EC.presence_of_element_located((By.ID, "ServicoPrestado_Descricao"))
        )
        self.esperar_loading_sumir()
        time.sleep(1)

        # ==========================
        # MUNICÍPIO
        # ==========================
        self._log("🌎 Selecionando município...")

        campo_municipio = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "#pnlLocalPrestacao span.selection > span")
            )
        )

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            campo_municipio
        )

        campo_municipio.click()

        campo_busca = wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "span input.select2-search__field")
            )
        )

        campo_busca.send_keys(dados_nota.get("municipio", "Afogados da Ingazeira/PE"))

        time.sleep(2)
        campo_busca.send_keys(Keys.ENTER)

        # ==========================
        # CTN
        # ==========================
        self._log("🏷️ Selecionando CTN...")

        campo_ctn = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "#pnlServicoPrestado span.selection > span")
            )
        )

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            campo_ctn
        )

        time.sleep(1)
        campo_ctn.click()

        campo_busca = wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "span input.select2-search__field")
            )
        )

        campo_busca.clear()
        campo_busca.send_keys(dados_nota.get("ctn", ""))

        time.sleep(2)
        campo_busca.send_keys(Keys.ENTER)

        # ==========================
        # NÃO INCIDÊNCIA
        # ==========================
        self._log("⚖️ Marcando não incidência...")

        radio_nao = wait.until(
            EC.presence_of_element_located(
                (By.ID, "ServicoPrestado_HaExportacaoImunidadeNaoIncidencia")
            )
        )

        driver.execute_script("arguments[0].click();", radio_nao)
        time.sleep(1)
        # ==========================
        # NBS
        # ==========================
        self._log("🔢 Selecionando NBS...")

        campo_nbs = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "#ServicoPrestado_CodigoNBS_chosen span")
            )
        )

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            campo_nbs
        )

        time.sleep(1)
        campo_nbs.click()

        campo_busca = wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "#ServicoPrestado_CodigoNBS_chosen input")
            )
        )

        campo_busca.clear()
        campo_busca.send_keys(dados_nota.get("nbs", ""))

        time.sleep(2)

        resultado = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "#ServicoPrestado_CodigoNBS_chosen ul li")
            )
        )

        resultado.click()

        self._log("⏳ Aguardando sistema após NBS...")

        # 🔥 AGUARDA RECARREGAMENTO REAL
        wait.until(
            EC.presence_of_element_located((By.ID, "ServicoPrestado_Descricao"))
        )

        time.sleep(2)

        # 🔥 AGUARDA O CAMPO ESTAR ATIVO DE NOVO
        campo_desc = wait.until(
            EC.element_to_be_clickable((By.ID, "ServicoPrestado_Descricao"))
        )
        # ==========================
        # DEBUG DESCRIÇÃO
        # ==========================
        descricao_original = dados_nota.get("descricao", "")
        self._log(f"📝 Descrição original: {descricao_original}")
        descricao_limpa = self.limpar_descricao(descricao_original)
        self._log(f"🧹 Descrição limpa: {descricao_limpa}")

        self._log("✍️ Tentando preencher campo descrição...")

        campo_desc.click()
        time.sleep(1)

        campo_desc.clear()
        campo_desc.send_keys(descricao_limpa)

        time.sleep(1)

        valor = campo_desc.get_attribute("value")
        self._log(f"📌 Valor no campo após tentativa: '{valor}'")
        # ==========================
        # BOTÃO AVANÇAR
        # ==========================
        self._log("➡️ Clicando no botão Avançar...")

        botao_avancar = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(.,'Avançar')]")
            )
        )

        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            botao_avancar
        )

        time.sleep(1)

        try:
            botao_avancar.click()
        except:
            self._log("⚠ Clique normal falhou, usando JS...")
            driver.execute_script("arguments[0].click();", botao_avancar)

        self._log("✅ Página 2 concluída")
    # PÁGINA 3
    @etapa_automacao("Página 3", tentativas=3, espera_segundos=2)
    def preencher_pagina_3(self, dados_nota: dict):

        self._log("💰 Preenchendo Página 3...")

        wait = self.wait
        driver = self.driver

        # ==========================
        # AGUARDAR CARREGAMENTO
        # ==========================
        wait.until(
            EC.presence_of_element_located((By.ID, "Valores_ValorServico"))
        )
        self.esperar_loading_sumir()

        # ==========================
        # VALOR DO SERVIÇO
        # ==========================
        valor = dados_nota.get("valor", 0)

        self._log("💵 Preenchendo valor do serviço...")


        campo_valor = wait.until(
            EC.element_to_be_clickable((By.ID, "Valores_ValorServico"))
        )

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            campo_valor
        )

        campo_valor.click()
        time.sleep(0.5)

        valor = dados_nota.get("valor", 0)

        campo_valor.clear()
        campo_valor.send_keys(str(valor).replace(".", ","))

        # 🔥 ESSENCIAL
        campo_valor.send_keys(Keys.TAB)

        self._log("⏳ Aguardando habilitação dos campos...")
        time.sleep(1)

        # ==========================
        # EXIGIBILIDADE = NÃO
        # ==========================
        self._log("⚖️ Selecionando Exigibilidade = Não")

        radio_exigibilidade = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//label[contains(.,'Não')]")
            )
        )

        driver.execute_script("arguments[0].click();", radio_exigibilidade)


        # ==========================
        # RETENÇÃO = SIM
        # ==========================
        self._log("📌 Selecionando Retenção = Sim")

        radio_ret = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//input[@name='ISSQN.HaRetencao' and @value='1']")
            )
        )

        driver.execute_script("""
            arguments[0].checked = true;
            arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
        """, radio_ret)

        self._log("✅ Retenção marcada como SIM")


        # ==========================
        # AGUARDAR PAINEL
        # ==========================
        self._log("⏳ Aguardando painel de retenção...")

        wait.until(
            EC.presence_of_element_located((By.ID, "pnlRetencao"))
        )

        time.sleep(1)


        # ==========================
        # TOMADOR (CORRIGIDO)
        # ==========================
        self._log("👤 Selecionando Retido pelo Tomador")

        radio_tomador = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//input[@name='ISSQN.TipoRetencao' and @value='2']")
            )
        )

        driver.execute_script("""
            arguments[0].checked = true;
            arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
        """, radio_tomador)

        self._log("✅ Tomador selecionado")

        time.sleep(2)


        # ==========================
        # BENEFÍCIO MUNICIPAL = NÃO
        # ==========================
        self._log("🏛️ Selecionando Benefício Municipal = Não")

        radio_beneficio = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//input[@name='ISSQN.HaBeneficioMunicipal' and @value='0']")
            )
        )

        driver.execute_script("""
            arguments[0].checked = true;
            arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
        """, radio_beneficio)

        self._log("✅ Benefício municipal marcado como NÃO")

        time.sleep(2)


        # ==========================
        # DEDUÇÃO / REDUÇÃO = NÃO
        # ==========================
        self._log("📉 Selecionando Dedução/Redução = Não")

        radio_deducao = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//input[@name='ISSQN.HaDeducaoReducao' and @value='0']")
            )
        )

        driver.execute_script("""
            arguments[0].checked = true;
            arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
        """, radio_deducao)

        self._log("✅ Dedução/Redução marcada como NÃO")

        time.sleep(2)

        # ================================
        # PIS / COFINS - Situação Tributária
        # ================================

        print("Selecionando Situação Tributária do PIS/COFINS...")

        # scroll até a seção
        elemento_pis = driver.find_element(By.ID, "TributacaoFederal_PISCofins_SituacaoTributaria")
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elemento_pis)

        driver.execute_script("""
        var selectId = "TributacaoFederal_PISCofins_SituacaoTributaria";
        var textoDesejado = "00 - Nenhum";

        var select = document.getElementById(selectId);

        if(select){

            // 1. Encontrar o option correto pelo TEXTO
            var encontrado = false;
            for (var i = 0; i < select.options.length; i++) {
                if (select.options[i].text.trim() === textoDesejado) {
                    select.selectedIndex = i;
                    encontrado = true;
                    break;
                }
            }

            // 2. Disparar change
            select.dispatchEvent(new Event('change', { bubbles: true }));

            // 3. Atualizar CHOSEN corretamente
            if (window.jQuery && jQuery(select).data('chosen')) {
                jQuery(select).trigger('chosen:updated');
            }

            // 4. FORÇA BRUTA (garantia 100%)
            var chosen = document.getElementById(selectId + "_chosen");
            if (chosen) {
                var itens = chosen.querySelectorAll("li");
                itens.forEach(function(item){
                    if (item.innerText.trim() === textoDesejado){
                        item.click();
                    }
                });
            }
        }
        """)

        print("Situação Tributária do PIS/COFINS definida como: 00 - Nenhum")

        # ================================
        # Tipo de retenção PIS/COFINS/CSLL
        # ================================

        print("Selecionando Tipo de retenção PIS/COFINS/CSLL...")

        # scroll até o elemento
        elemento_tipo = driver.find_element(By.ID, "TributacaoFederal_PISCofins_TipoRetencao")
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elemento_tipo)

        driver.execute_script("""
        var selectId = "TributacaoFederal_PISCofins_TipoRetencao";
        var textoDesejado = "PIS/COFINS/CSLL Não Retidos";

        var select = document.getElementById(selectId);

        if(select){

            // 1. Seleciona pelo TEXTO (forma segura)
            for (var i = 0; i < select.options.length; i++) {
                if (select.options[i].text.trim() === textoDesejado) {
                    select.selectedIndex = i;
                    break;
                }
            }

            // 2. Dispara change
            select.dispatchEvent(new Event('change', { bubbles: true }));

            // 3. Atualiza CHOSEN
            if (window.jQuery && jQuery(select).data('chosen')) {
                jQuery(select).trigger('chosen:updated');
            }

            // 4. GARANTIA TOTAL (força clique no CHOSEN)
            var chosen = document.getElementById(selectId + "_chosen");
            if (chosen) {
                var itens = chosen.querySelectorAll("li");
                itens.forEach(function(item){
                    if (item.innerText.trim() === textoDesejado){
                        item.click();
                    }
                });
            }
        }
        """)

        print("Tipo de retenção definido como: PIS/COFINS/CSLL Não Retidos")

        # ================================
        # IRRF
        # ================================
        valor_ir = dados_nota.get("ir", 0)

        self._log(f"💸 Preenchendo IRRF: {valor_ir}")

        if valor_ir > 0:

            campo_irrf = wait.until(
                EC.presence_of_element_located(
                    (By.ID, "TributacaoFederal_ValorIRRF")
                )
            )

            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                campo_irrf
            )

            # 🔥 limpar via JS (mais seguro)
            driver.execute_script("""
            var campo = document.getElementById("TributacaoFederal_ValorIRRF");
            if(campo){
                campo.value = "";
            }
            """)

            campo_irrf.send_keys(str(valor_ir).replace(".", ","))

            self._log("✅ IRRF preenchido")

        else:
            self._log("⚠ IRRF = 0 (ignorado)")

        time.sleep(2)
        # ================================
        # AVANÇAR
        # ================================
        self._log("➡️ Avançando para próxima etapa...")

        botao_avancar = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[.//span[contains(text(),'Avançar')]]")
            )
        )

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            botao_avancar
        )

        time.sleep(2)

        botao_avancar.click()

        self._log("✅ Página 3 FINALIZADA")
    def revisar_pagina_4(self) -> str:
        """
        Etapa de revisão final da nota (Página 4).
        Compatível com UI (callback) e terminal (fallback).
        """

        self._log("\n==============================")
        self._log("REVISÃO FINAL - PÁGINA 4")
        self._log("==============================")

        self._log("Verifique os dados da nota no navegador.")
        self._log("Se precisar corrigir algo na planilha, faça agora.")
        self._log("")
        self._log("1 - Emitir a nota")
        self._log("2 - Corrigir dados da Página 2")
        self._log("3 - Corrigir dados da Página 3")
        self._log("4 - Cancelar operação")

        # ===============================
        # 🔥 MODO INTERFACE (PRINCIPAL)
        # ===============================
        if hasattr(self, "input_callback") and self.input_callback:

            self._log("🧠 Aguardando decisão do usuário pela interface...")

            opcao = self.input_callback({
                "tipo": "revisao_nf",
                "mensagem": "Escolha ação",
                "opcoes": [
                    {"id": "1", "label": "Emitir"},
                    {"id": "2", "label": "Corrigir Página 2"},
                    {"id": "3", "label": "Corrigir Página 3"},
                    {"id": "4", "label": "Cancelar"},
                ]
            })

            self._log(f"Opção selecionada (UI): {opcao}")
            return opcao

        # ===============================
        # 🖥️ MODO TERMINAL (FALLBACK)
        # ===============================
        while True:
            opcao = input("\nDigite a opção desejada: ").strip()

            if opcao in ["1", "2", "3", "4"]:
                self._log(f"Opção selecionada: {opcao}")
                return opcao

            self._log("Opção inválida. Digite novamente.")
    def _garantir_nome_unico(self, caminho_arquivo: str) -> str:
        base, ext = os.path.splitext(caminho_arquivo)
        contador = 1

        novo_caminho = caminho_arquivo

        while os.path.exists(novo_caminho):
            novo_caminho = f"{base}_{contador}{ext}"
            contador += 1

        return novo_caminho
    def _montar_pasta_destino(self, dados_nota: dict) -> str:

        cliente = str(dados_nota.get("cliente", "CLIENTE")).strip().upper()
        especie = str(dados_nota.get("especie", "GERAL")).strip().upper()

        # 🔥 VINDO DA INTERFACE
        municipio = self.municipio
        ano = self.ano
        mes = self.mes

        pasta_destino = os.path.join(
            self.pasta_saida_base,   # 🔥 CORREÇÃO AQUI
            ano,
            mes,
            municipio,
            cliente,
            especie
        )

        os.makedirs(pasta_destino, exist_ok=True)

        return pasta_destino
    def fluxo_simulado_pos_emissao(self, dados_nota: dict) -> dict:
        self._log("🧪 MODO SIMULAÇÃO ATIVO")
        self._log("🚫 Nenhuma nota será emitida de verdade")

        numero_nf = f"TESTE-{int(time.time())}"
        self._log(f"🧾 Número simulado da NFS-e: {numero_nf}")

        cliente = str(dados_nota.get("cliente", "CLIENTE")).strip().upper()
        mes = str(dados_nota.get("mes", "MES")).strip().upper()
        ano = str(dados_nota.get("ano", "2026")).strip()

        pasta_temp = os.path.join(self.caminho_base, "_temp_download")
        os.makedirs(pasta_temp, exist_ok=True)

        caminho_pdf_temp = os.path.join(pasta_temp, "arquivo_fake.pdf")
        caminho_xml_temp = os.path.join(pasta_temp, "arquivo_fake.xml")

        with open(caminho_pdf_temp, "w", encoding="utf-8") as f:
            f.write("PDF TESTE - SIMULAÇÃO DE DOWNLOAD")

        with open(caminho_xml_temp, "w", encoding="utf-8") as f:
            f.write("<xml>TESTE - SIMULAÇÃO DE DOWNLOAD</xml>")

        self._log("📥 Download simulado concluído")

        nome_base = f"NF_{numero_nf}_{cliente}_{mes}_{ano}"
        nome_pdf = f"{nome_base}.pdf"
        nome_xml = f"{nome_base}.xml"

        pasta_destino = self._montar_pasta_destino(dados_nota)

        destino_pdf = os.path.join(pasta_destino, nome_pdf)
        destino_xml = os.path.join(pasta_destino, nome_xml)

        destino_pdf = self._garantir_nome_unico(destino_pdf)
        destino_xml = self._garantir_nome_unico(destino_xml)

        shutil.move(caminho_pdf_temp, destino_pdf)
        shutil.move(caminho_xml_temp, destino_xml)

        self._log(f"✅ PDF salvo em: {destino_pdf}")
        self._log(f"✅ XML salvo em: {destino_xml}")
        self._log("📂 Organização de arquivos concluída com sucesso")

        return {
            "sucesso": True,
            "numero_nfse": numero_nf,
            "caminho_pdf": destino_pdf,
            "caminho_xml": destino_xml
        }
    # EMISSÃO PRINCIPAL
    @etapa_automacao("Confirmar Emissão", tentativas=2, espera_segundos=2)
    def emitir_nota(self, dados_nota: dict, contexto: dict) -> dict:

        item = str(dados_nota.get("item", "")).strip()

        self._log(f"Iniciando emissão do ITEM {item}")

        inicio = time.time()

        try:
            # 🚨 NÃO FAZ LOGIN AQUI

            self.acessar_tela_emissao()

            self.preencher_pagina_1(dados_nota)
            self.preencher_pagina_2(dados_nota)
            self.preencher_pagina_3(dados_nota)

            item_id = str(dados_nota.get("item"))

            # ===============================
            # 🔁 LOOP DE REVISÃO (NOVO)
            # ===============================
            while True:

                opcao = self.revisar_pagina_4()

                if opcao == "1":

                    if self.modo_teste:
                        self._log("🧪 MODO TESTE - SIMULANDO EMISSÃO")

                        numero_fake = f"TESTE-{int(time.time())}"

                        resultado = {
                            "numero_nfse": numero_fake
                        }

                        break

                    else:
                        self._log("Confirmando emissão da nota...")
                        resultado = self.confirmar_emissao_e_capturar_retorno(dados_nota)
                        break

                elif opcao == "2":
                    self._log("Usuário escolheu corrigir Página 2 (planilha)")

                    dados_nota = self.obter_dados_item(item_id)

                    self.voltar_para_pagina_2()
                    self.preencher_pagina_2(dados_nota)
                    self.preencher_pagina_3(dados_nota)

                elif opcao == "3":
                    self._log("Usuário escolheu corrigir Página 3 (planilha)")

                    dados_nota = self.obter_dados_item(item_id)

                    self.voltar_para_pagina_3()
                    self.preencher_pagina_3(dados_nota)

                elif opcao == "4":
                    self._log("Operação cancelada pelo usuário")

                    return {
                        "sucesso": False,
                        "status": "CANCELADA",
                        "mensagem": "Cancelado pelo usuário"
                    }

            # ===============================
            # CONTINUA NORMAL
            # ===============================
            numero_nfse = resultado["numero_nfse"]

            if self.modo_teste:
                self._log("📥 Simulando download de arquivos...")

                caminho_pdf, caminho_xml = self._simular_download_e_organizacao(
                    numero_nfse, dados_nota
                )

            else:
                caminho_pdf, caminho_xml = self.organizar_arquivos_emitidos(
                    numero_nfse, item, contexto
                )
            print("DEBUG PDF:", caminho_pdf)
            print("DEBUG XML:", caminho_xml)
            fim = time.time()

            return {
                "sucesso": True,
                "status": "EMITIDA",
                "numero_nfse": numero_nfse,
                "tempo_execucao": round(fim - inicio, 2),
                "caminho_xml": caminho_xml,
                "caminho_pdf": caminho_pdf,
                "mensagem": ""
            }

        except Exception as e:

            fim = time.time()

            self._log(f"Erro ITEM {item}: {e}")

            return {
                "sucesso": False,
                "status": "ERRO",
                "mensagem": str(e),
                "tempo_execucao": round(fim - inicio, 2),
                }
    def voltar_para_pagina_3(self):
        self._log("Voltando para Página 3...")

        wait = WebDriverWait(self.driver, 20)

        botao_voltar = wait.until(
            EC.element_to_be_clickable((By.ID, "btnVoltar"))
        )

        self.driver.execute_script("arguments[0].click();", botao_voltar)

        self._log("Retornou para Página 3.")
    def voltar_para_pagina_2(self):

        self._log("Voltando para Página 2...")

        self.voltar_para_pagina_3()
        time.sleep(1)
        self.voltar_para_pagina_3()

        self._log("Retornou para Página 2.")
    def _carregar_planilha(self):

        if not self.caminho_base:
            raise Exception("Caminho da planilha não definido")

        if not os.path.exists(self.caminho_base):
            raise Exception(f"Planilha não encontrada: {self.caminho_base}")

        xls = pd.ExcelFile(self.caminho_base, engine="openpyxl")

        abas_normalizadas = [a.upper().strip() for a in xls.sheet_names]

        if "NOTAS" in abas_normalizadas:
            nome_aba_real = xls.sheet_names[
                abas_normalizadas.index("NOTAS")
            ]
        else:
            raise Exception("Aba 'NOTAS' não encontrada na planilha")

        df = pd.read_excel(
            self.caminho_base,
            sheet_name=nome_aba_real,
            engine="openpyxl"
        )

        # 🔥 padroniza colunas (evita erro tipo 'ITEM')
        df.columns = [c.strip().upper() for c in df.columns]

        return df
    def obter_dados_item(self, item_id):

        df = self._carregar_planilha()

        linha = df[df["ITEM"] == str(item_id)]

        if linha.empty:
            raise Exception(f"Item {item_id} não encontrado na planilha.")

        dados = linha.iloc[0].to_dict()

        self._log(f"Dados recarregados do item {item_id}")

        return dados
    def confirmar_emissao_e_capturar_retorno(self, dados_nota: dict) -> dict:

        wait = WebDriverWait(self.driver, 30)

        self._log("🚀 Confirmando emissão da NFS-e...")

        # 1. clicar emitir
        botao_emitir = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[.//span[contains(text(),'Emitir')]]")
            )
        )

        self.driver.execute_script("arguments[0].click();", botao_emitir)

        # 2. aguardar retorno (SUCESSO)
        self._log("⏳ Aguardando retorno da emissão...")

        elemento_retorno = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(),'NFS-e') or contains(text(),'Número')]")
            )
        )

        texto = elemento_retorno.text

        import re
        match = re.search(r"\d+", texto)

        if not match:
            raise EmissaoNaoAutorizadaErro("❌ Número da NFS-e não encontrado")

        numero_nfse = match.group()

        self._log(f"✅ NFS-e emitida: {numero_nfse}")

        return {"numero_nfse": numero_nfse}
    # ORGANIZAR ARQUIVOS
    def organizar_arquivos_emitidos(self, numero_nfse: str, item: str, contexto: dict):

        ano = contexto["ano"]
        mes = contexto["mes"]
        municipio = contexto["municipio"]

        pasta = Path(self.pasta_saida_base) / ano / mes / municipio / "Emitidas"
        pasta.mkdir(parents=True, exist_ok=True)

        nome = f"NFSE_{numero_nfse}_{item}"

        caminho_pdf = str(pasta / f"{nome}.pdf")
        caminho_xml = str(pasta / f"{nome}.xml")

        if not os.path.exists(caminho_pdf):
            with open(caminho_pdf, "wb") as f:
                f.write(b"")

        if not os.path.exists(caminho_xml):
            with open(caminho_xml, "wb") as f:
                f.write(b"")
            # 🔥 CORREÇÃO
        return caminho_pdf, caminho_xml

    def _simular_download_e_organizacao(self, numero_nfse, dados_nota):

        print("🔥 FUNÇÃO DE DOWNLOAD EXECUTADA")
        print("caminho_base:", self.caminho_base)

        self._log("🧪 Criando arquivos simulados...")

        cliente = str(dados_nota.get("cliente", "CLIENTE")).strip().upper()
        especie = str(dados_nota.get("especie", "GERAL")).strip().upper()

        # ==========================
        # 📂 BASE = PASTA DO EXCEL
        # ==========================
        pasta_base = Path(self.caminho_base).parent

        # ==========================
        # 📁 TEMP (dentro da base)
        # ==========================
        pasta_temp = pasta_base / "_temp"
        pasta_temp.mkdir(parents=True, exist_ok=True)

        caminho_pdf_temp = pasta_temp / "fake.pdf"
        caminho_xml_temp = pasta_temp / "fake.xml"

        caminho_pdf_temp.write_text("PDF SIMULADO")
        caminho_xml_temp.write_text("<xml>SIMULADO</xml>")

        # ==========================
        # 📁 DESTINO FINAL (SEU PADRÃO)
        # ==========================
        pasta_destino = pasta_base / cliente / especie
        pasta_destino.mkdir(parents=True, exist_ok=True)

        nome_base = f"NF_{numero_nfse}_{cliente}"

        destino_pdf = pasta_destino / f"{nome_base}.pdf"
        destino_xml = pasta_destino / f"{nome_base}.xml"

        shutil.move(str(caminho_pdf_temp), str(destino_pdf))
        shutil.move(str(caminho_xml_temp), str(destino_xml))

        print("🔥 SALVO EM:", pasta_destino)

        self._log("📂 Arquivos simulados organizados")

        return str(destino_pdf), str(destino_xml)