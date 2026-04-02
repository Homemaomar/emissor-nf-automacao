from envio import EnvioService

caminho_planilha = r"C:\Users\Antônio Marcos\Desktop\Notas\2026\02 - Fevereiro\Afogados da Ingazeira\notas.xlsm"

email_config = {
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_user": "mbs.busiines@gmail.com",
    smtp_password = os.getenv("SMTP_PASSWORD"),
    "remetente_nome": "Setor Fiscal",
    "use_tls": True
}

service = EnvioService(
    caminho_planilha=caminho_planilha,
    nome_aba="NOTAS",
    email_config=email_config,
    log_callback=print,
    limite_por_minuto=5,
    max_tentativas=2
)

service.processar_envios(
    enviar_email=True,
    enviar_whatsapp=True
)
