import os
from datetime import datetime


def normalizar_texto(valor):
    if not valor:
        return ""

    valor = str(valor).strip()

    # 🔥 REMOVE ASPAS E ESPAÇOS ESCONDIDOS
    valor = valor.replace('"', '').replace("'", "")

    return valor


def normalizar_status(valor, padrao="PENDENTE") -> str:
    texto = normalizar_texto(valor).upper()
    return texto if texto else padrao


def normalizar_tipo_envio(valor) -> str:
    texto = normalizar_texto(valor).upper()
    if texto in ("EMAIL", "WHATSAPP", "AMBOS"):
        return texto
    return "AMBOS"


def normalizar_flag_sim_nao(valor, padrao="SIM") -> str:
    texto = normalizar_texto(valor).upper()
    if texto in ("SIM", "NÃO", "NAO"):
        return "NÃO" if texto == "NAO" else texto
    return padrao


def agora_str() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def arquivo_existe(caminho: str) -> bool:
    return bool(caminho) and os.path.exists(caminho)