from pathlib import Path
from datetime import datetime


def registrar_log(cnpj, valor, status, mensagem=""):
    pasta_logs = Path("logs")
    pasta_logs.mkdir(exist_ok=True)

    arquivo_log = pasta_logs / "emissao_log.txt"
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    linha = f"[{agora}] | CNPJ: {cnpj} | VALOR: {valor} | STATUS: {status}"
    if mensagem:
        linha += f" | DETALHE: {mensagem}"

    with open(arquivo_log, "a", encoding="utf-8") as f:
        f.write(linha + "\n")