from automacao.navegacao import abrir_emissao_completa
import time


def recuperar_fluxo(driver):

    print("\n⚠ Tentando recuperar fluxo do robô...")

    try:

        driver.refresh()

        time.sleep(3)

        abrir_emissao_completa(driver)

        print("✅ Fluxo recuperado com sucesso.")

        return True

    except Exception as erro:

        print("❌ Falha ao recuperar fluxo:", erro)

        return False

def executar_com_retry(funcao, tentativas=3):

    for tentativa in range(1, tentativas + 1):

        try:

            return funcao()

        except Exception as erro:

            print(f"\n⚠ Erro na tentativa {tentativa}: {erro}")

            if tentativa == tentativas:
                raise erro

            print("🔄 Tentando novamente...")