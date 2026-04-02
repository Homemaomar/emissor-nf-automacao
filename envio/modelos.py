from dataclasses import dataclass
from typing import Optional


from dataclasses import dataclass

@dataclass
class NotaEnvio:

    # 🔹 SEM DEFAULT PRIMEIRO
    linha_excel: int
    item: str
    cliente: str
    secretaria: str
    valor: float
    especie: str
    email: str
    nome_contato: str
    whatsapp: str
    status: str
    status_email: str
    status_whatsapp: str
    caminho_pdf: str
    caminho_xml: str

    # 🔹 COM DEFAULT SEMPRE NO FINAL
    descricao: str = ""
    numero_nfse: str = ""
    mes: str = ""
    ano: str = ""
    municipio: str = ""
    tipo_envio: str = "AMBOS"
    enviar_automatico: str = "SIM"


@dataclass
class ResultadoEnvio:
    sucesso: bool
    mensagem: str
    protocolo: str = ""