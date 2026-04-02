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

import time

print("Sistema Emissor de Nota Fiscal iniciado.")

# 1️⃣ iniciar navegador
driver = iniciar_navegador()

# 2️⃣ login no portal
realizar_login(driver)

# 3️⃣ navegar até emissão completa
abrir_emissao_completa(driver)

# dados de teste
dados_teste = {
    "cnpj": "11.350.659/0001-94",
    "municipio": "Afogados da Ingazeira/PE",
    "ctn": "100202",
    "nbs": "110011210",
    "descricao": "Serviço de transporte escolar",

    "valor_servico": "190000",
    "irrf": "150"
}

# 4️⃣ página 1
print("\nExecutando Página 1...")
preencher_pagina1(driver, dados_teste)

# 5️⃣ página 2
print("\nExecutando Página 2...")
preencher_pagina2(driver, dados_teste)

# 6️⃣ página 3
print("\nExecutando Página 3...")
preencher_pagina3(driver, dados_teste)

# 7️⃣ revisão na página 4
opcao = revisar_pagina4()

print("\nOpção escolhida:", opcao)

# LOOP DE REVISÃO
while True:

    opcao = revisar_pagina4()

    if opcao == "1":
        print("Usuário decidiu emitir a nota.")
        break

    elif opcao == "2":
        print("Usuário quer corrigir dados da Página 2.")
        # ainda vamos implementar
        break

    elif opcao == "3":

        print("Voltando para Página 3 para correção...")

        voltar_para_pagina3(driver)

        print("Executando novamente Página 3...")
        preencher_pagina3(driver, dados_teste)

        print("Retornando para revisão...")

    elif opcao == "4":
        print("Operação cancelada pelo usuário.")
        break

# pausa para visualização
time.sleep(120)

