from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
import time

def selecionar_chosen(driver, wait, campo_id, valor):

    # clicar no container do chosen
    container = wait.until(
        EC.element_to_be_clickable(
            (By.ID, f"{campo_id}_chosen")
        )
    )

    container.click()

    # esperar campo de busca aparecer
    busca = wait.until(
        EC.visibility_of_element_located(
            (By.CSS_SELECTOR, ".chosen-container-active input")
        )
    )

    busca.clear()
    busca.send_keys(valor)

    # selecionar opção
    opcao = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, ".chosen-results li")
        )
    )

    opcao.click()

def preencher_pagina1(driver, dados):

    wait = WebDriverWait(driver, 20)

    print("Preenchendo página 1 da nota...")

    # DATA DE COMPETÊNCIA
    campo_data = wait.until(
        EC.presence_of_element_located((By.ID, "DataCompetencia"))
    )

    campo_data.clear()

    data_hoje = datetime.today().strftime("%d/%m/%Y")

    campo_data.send_keys(data_hoje)
    campo_data.send_keys(Keys.TAB)

    time.sleep(1)

    # RADIO TOMADOR BRASIL
    radio_brasil = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//label[contains(.,'Brasil')]"))
    )

    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});",
        radio_brasil
    )

    time.sleep(1)

    radio_brasil.click()

    print("Radio Brasil selecionado")

    # ESPERAR CAMPO CNPJ
    campo_cnpj = wait.until(
        EC.visibility_of_element_located((By.ID, "Tomador_Inscricao"))
    )

    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});",
        campo_cnpj
    )

    campo_cnpj.click()

    campo_cnpj.send_keys(dados["cnpj"])
    campo_cnpj.send_keys(Keys.TAB)

    print("CNPJ inserido")

    time.sleep(2)

    # BOTÃO AVANÇAR
    botao_avancar = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Avançar')]"))
    )

    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});",
        botao_avancar
    )

    time.sleep(1)

    botao_avancar.click()

    print("Página 1 concluída.")

def preencher_pagina2(driver, dados):

    wait = WebDriverWait(driver, 30)

    print("Preenchendo página 2...")

    # esperar a página 2 carregar
    wait.until(
        EC.presence_of_element_located((By.ID, "ServicoPrestado_Descricao"))
    )
    time.sleep(2)

    # ==========================
    # MUNICÍPIO
    # ==========================

    campo_municipio = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "#pnlLocalPrestacao span.selection > span")
        )
    )

    campo_municipio.click()

    # campo de busca do select2
    campo_busca = wait.until(
        EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "span input.select2-search__field")
        )
    )

    campo_busca.send_keys("Afogados da Ingazeira/PE")

    time.sleep(2)

    campo_busca.send_keys(Keys.ENTER)

    print("Município selecionado")

    # ==========================
    # CÓDIGO DE TRIBUTAÇÃO NACIONAL (CTN)
    # ==========================

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

    # campo de busca do Select2
    campo_busca = wait.until(
        EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "span input.select2-search__field")
        )
    )

    campo_busca.clear()

    campo_busca.send_keys(dados["ctn"])

    time.sleep(2)

    campo_busca.send_keys(Keys.ENTER)

    print("Código de tributação selecionado")

    # ==========================
    # NÃO INCIDÊNCIA
    # ==========================
    radio_nao = wait.until(
        EC.presence_of_element_located(
            (By.ID, "ServicoPrestado_HaExportacaoImunidadeNaoIncidencia")
        )
    )

    driver.execute_script("arguments[0].click();", radio_nao)

    print("Selecionado: Não incidência")
    time.sleep(1)

    # ==========================
    # DESCRIÇÃO
    # ==========================
    campo_desc = wait.until(
        EC.presence_of_element_located((By.ID, "ServicoPrestado_Descricao"))
    )

    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});",
        campo_desc
    )
    time.sleep(1)

    driver.execute_script(
        "arguments[0].removeAttribute('readonly');",
        campo_desc
    )

    campo_desc.clear()
    campo_desc.send_keys(dados["descricao"])

    print("Descrição inserida")

    # ==========================
    # NBS
    # ==========================

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

    # campo de busca do chosen
    campo_busca = wait.until(
        EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "#ServicoPrestado_CodigoNBS_chosen input")
        )
    )

    campo_busca.clear()
    campo_busca.send_keys(dados["nbs"])

    time.sleep(2)

    # selecionar primeiro resultado
    resultado = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "#ServicoPrestado_CodigoNBS_chosen ul li")
        )
    )

    resultado.click()

    print("NBS selecionado")

    # ==========================
    # BOTÃO AVANÇAR
    # ==========================

    botao_avancar = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(.,'Avançar')]")
        )
    )

    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});",
        botao_avancar
    )

    time.sleep(1)

    botao_avancar.click()

    print("Página 2 concluída. Indo para página 3...")

def preencher_pagina3(driver, dados):

    wait = WebDriverWait(driver, 20)

    print("Preenchendo Página 3")

    # ===============================
    # VALOR DO SERVIÇO
    # ===============================
    campo_valor = wait.until(
        EC.element_to_be_clickable((By.ID, "Valores_ValorServico"))
    )

    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});",
        campo_valor
    )

    campo_valor.clear()
    campo_valor.send_keys(dados["valor_servico"])

    print("Valor do serviço preenchido")

    # ===============================
    # EXIGIBILIDADE DO ISSQN
    # NÃO
    # ===============================

    print("Selecionando Exigibilidade = Não")

    radio_exig = wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//input[@type='radio' and @value='0']")
        )
    )

    driver.execute_script("""
        arguments[0].checked = true;
        arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
    """, radio_exig)

    print("Exigibilidade marcada como NÃO")

    # ===============================
    # HÁ RETENÇÃO DO ISSQN
    # SIM
    # ===============================

    print("Selecionando Retenção = Sim")

    radio_ret = wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//input[@name='ISSQN.HaRetencao' and @value='1']")
        )
    )

    driver.execute_script("""
        arguments[0].checked = true;
        arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
    """, radio_ret)

    print("Retenção marcada como SIM")

    print("Aguardando painel de retenção aparecer...")

    wait.until(
        EC.presence_of_element_located((By.ID, "pnlRetencao"))
    )

    print("Selecionando: Retido pelo Tomador")

    radio_tomador = wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//input[@name='ISSQN.TipoRetencao' and @value='2']")
        )
    )

    driver.execute_script("""
        arguments[0].checked = true;
        arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
    """, radio_tomador)

    print("Tomador selecionado")

    print("Selecionando Benefício Municipal = Não")

    radio_beneficio = wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//input[@name='ISSQN.HaBeneficioMunicipal' and @value='0']")
        )
    )

    driver.execute_script("""
        arguments[0].checked = true;
        arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
    """, radio_beneficio)

    print("Benefício municipal marcado como NÃO")

    print("Selecionando Dedução/Redução = Não")

    radio_deducao = wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//input[@name='ISSQN.HaDeducaoReducao' and @value='0']")
        )
    )

    driver.execute_script("""
        arguments[0].checked = true;
        arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
    """, radio_deducao)

    print("Dedução/Redução marcada como NÃO")

    # ================================
    # PIS / COFINS - Situação Tributária
    # ================================

    print("Selecionando Situação Tributária do PIS/COFINS...")

    # scroll até a seção
    elemento_pis = driver.find_element(By.ID, "TributacaoFederal_PISCofins_SituacaoTributaria")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elemento_pis)

    driver.execute_script("""
    var select = document.getElementById("TributacaoFederal_PISCofins_SituacaoTributaria");

    if(select){
        select.value = "0";
        var event = new Event('change', {bubbles:true});
        select.dispatchEvent(event);
    }
    """)

    print("Situação Tributária do PIS/COFINS definida como: 00 - Nenhum")


    # ================================
    # Tipo de retenção PIS/COFINS/CSLL
    # ================================

    print("Selecionando Tipo de retenção PIS/COFINS/CSLL...")

    elemento_ret = driver.find_element(By.ID, "TributacaoFederal_PISCofins_TipoRetencao")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elemento_ret)

    driver.execute_script("""
    var select = document.getElementById("TributacaoFederal_PISCofins_TipoRetencao");

    if(select){
        select.value = "0";
        var event = new Event('change', {bubbles:true});
        select.dispatchEvent(event);
    }
    """)

    print("Tipo de retenção definido como: Sem retenção")


    # ================================
    # IRRF
    # ================================

    print("Preenchendo valor do IRRF...")

    campo_irrf = wait.until(
        EC.element_to_be_clickable((By.ID, "TributacaoFederal_ValorIRRF"))
    )

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", campo_irrf)

    print("Preenchendo valor do IRRF...")

    campo_irrf = wait.until(
        EC.presence_of_element_located((By.ID, "TributacaoFederal_ValorIRRF"))
    )

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", campo_irrf)

    driver.execute_script("""
    var campo = document.getElementById("TributacaoFederal_ValorIRRF");
    if(campo){
        campo.value = "";
    }
    """)

    campo_irrf.send_keys(dados["irrf"])

    print(f"IRRF preenchido com valor: {dados['irrf']}")

    print("Clicando no botão Avançar...")

    botao_avancar = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, "//button[.//span[contains(text(),'Avançar')]]")
        )
    )

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", botao_avancar)

    driver.execute_script("arguments[0].click();", botao_avancar)

    print("Página 3 concluída. Indo para a próxima etapa...")

def revisar_pagina4():
    print("\n==============================")
    print("REVISÃO FINAL - PÁGINA 4")
    print("==============================")

    print("\nVerifique os dados da nota no navegador.")
    print("Se precisar corrigir algo na planilha, faça agora.")

    print("\nEscolha uma opção:")
    print("1 - Emitir a nota")
    print("2 - Corrigir dados da Página 2")
    print("3 - Corrigir dados da Página 3")
    print("4 - Cancelar operação")

    while True:

        opcao = input("\nDigite a opção desejada: ").strip()

        if opcao in ["1", "2", "3", "4"]:
            return opcao

        print("Opção inválida. Digite novamente.")

def voltar_para_pagina3(driver):

    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    wait = WebDriverWait(driver, 20)

    print("\nVoltando para Página 3...")

    botao_voltar = wait.until(
        EC.element_to_be_clickable(
            (By.ID, "btnVoltar")
        )
    )

    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});",
        botao_voltar
    )

    botao_voltar.click()

    print("Retornou para Página 3.")