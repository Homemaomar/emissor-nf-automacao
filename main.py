from automacao.navegador import iniciar_navegador
from automacao.login import realizar_login
from automacao.navegacao import abrir_emissao_completa
from automacao.emissao import (
    preencher_pagina1,
    preencher_pagina2,
    preencher_pagina3,
    revisar_pagina4,
    voltar_para_pagina3
)

from dados.leitura_planilha import ler_planilha_notas, atualizar_status_nota
from utils.logger import registrar_log
 from utils.recuperacao import recuperar_fluxo
import time

CAMINHO_PLANILHA = "planilhas/notas.xlsx"


# ================================
# MENU PRINCIPAL
# ================================

def menu():

    print("\n=================================")
    print("EMISSOR AUTOMÁTICO DE NFS-e")
    print("=================================")
    print("1 - Emitir uma nota de teste")
    print("2 - Emitir todas as notas da planilha")
    print("3 - Simulação (não emitir)")
    print("4 - Emitir por ITEM")
    print("5 - Sair")

    opcao = input("\nEscolha uma opção: ")

    return opcao


# ================================
# ESCOLHER ITENS
# ================================

def escolher_itens():

    entrada = input(
        "\nDigite os itens que deseja emitir (ex: 1 ou 1,1.3): "
    )

    itens = [i.strip() for i in entrada.split(",")]

    return itens


# ================================
# EXECUTAR EMISSÃO
# ================================

def executar_emissao(driver, dados, simulacao=False):

    try:

        print("\nExecutando Página 1...")
        preencher_pagina1(driver, dados)

        print("\nExecutando Página 2...")
        preencher_pagina2(driver, dados)

        print("\nExecutando Página 3...")
        preencher_pagina3(driver, dados)

        # LOOP DE REVISÃO

        while True:

            opcao = revisar_pagina4()

            if opcao == "1":

                if simulacao:
                    print("Modo simulação ativo. Nota não será emitida.")
                else:
                    print("Emitindo nota...")

                return "EMITIDA"

            elif opcao == "2":

                print("Correção da Página 2 ainda não implementada.")
                continue

            elif opcao == "3":

                print("Voltando para Página 3...")

                voltar_para_pagina3(driver)

                preencher_pagina3(driver, dados)

                print("Retornando para revisão...")

            elif opcao == "4":

                print("Operação cancelada.")

                return "CANCELADA"

            else:

                print("Opção inválida.")

    except Exception as erro:

        print("Erro durante emissão:", erro)

        return "ERRO"


# ================================
# EMISSÃO DE TESTE
# ================================

def emitir_teste(driver):

    dados_teste = {
        "cnpj": "11.350.659/0001-94",
        "municipio": "Afogados da Ingazeira/PE",
        "ctn": "100202",
        "nbs": "110011210",
        "descricao": "Serviço de transporte escolar",
        "valor_servico": "190000",
        "irrf": "150"
    }

    executar_emissao(driver, dados_teste)


# ================================
# EMISSÃO EM LOTE
# ================================

def emitir_lote(driver, simulacao=False):
    

    notas = ler_planilha_notas(CAMINHO_PLANILHA)

    if not notas:
        print("Nenhuma nota encontrada para emissão.")
        return    

    print(f"\n{len(notas)} notas pendentes encontradas.")

    for indice, dados in enumerate(notas, start=1):

        print("\n=================================")
        print(f"PROCESSANDO NOTA {indice}/{len(notas)}")
        print("=================================")

       

    try:

        status = executar_emissao(driver, dados)

        except Exception as erro:

            print("Erro detectado:", erro)

            sucesso = recuperar_fluxo(driver)

            if sucesso:

                print("Reiniciando emissão da nota...")

                status = executar_emissao(driver, dados)

            else:

                print("Não foi possível recuperar fluxo.")

                status = "ERRO"

            if not simulacao:

                atualizar_status_nota(
                    CAMINHO_PLANILHA,
                    dados["linha_excel"],
                    status
                )

                registrar_log(
                    dados["cnpj"],
                    dados["valor_servico"],
                    status
                )

            print("Preparando próxima emissão...")
            time.sleep(3)


# ================================
# EMISSÃO POR ITEM
# ================================

def emitir_por_item(driver):

    itens = escolher_itens()

    notas = ler_planilha_notas(CAMINHO_PLANILHA)

    notas_filtradas = []

    for nota in notas:

        if "item" in nota and nota["item"] in itens:
            notas_filtradas.append(nota)

    print(f"\n{len(notas_filtradas)} notas selecionadas.")

    for indice, dados in enumerate(notas_filtradas, start=1):

        print("\n=================================")
        print(f"PROCESSANDO ITEM {dados['item']}")
        print("=================================")

        status = executar_emissao(driver, dados)

        atualizar_status_nota(
            CAMINHO_PLANILHA,
            dados["linha_excel"],
            status
        )

        registrar_log(
            dados["cnpj"],
            dados["valor_servico"],
            status
        )

        time.sleep(3)


    # ================================
    # PROGRAMA PRINCIPAL
    # ================================

    print("Sistema Emissor de Nota Fiscal iniciado.")

    driver = iniciar_navegador()

    realizar_login(driver)

    abrir_emissao_completa(driver)


    while True:

        opcao = menu()

        if opcao == "1":

            emitir_teste(driver)

        elif opcao == "2":

            emitir_lote(driver)

        elif opcao == "3":

            emitir_lote(driver, simulacao=True)

        elif opcao == "4":

            emitir_por_item(driver)

        elif opcao == "5":

            print("Encerrando sistema.")
            break

        else:

            print("Opção inválida.")