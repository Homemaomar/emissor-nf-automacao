import logging
from pathlib import Path


def criar_logger_execucao(ano, mes, municipio):

    pasta_logs = Path("logs")
    pasta_logs.mkdir(exist_ok=True)

    nome_arquivo = f"{ano}-{mes}-{municipio.replace(' ', '_')}.log"
    caminho_log = pasta_logs / nome_arquivo

    logger = logging.getLogger(nome_arquivo)
    logger.setLevel(logging.INFO)

    if not logger.handlers:

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%d/%m/%Y %H:%M:%S"
        )

        file_handler = logging.FileHandler(caminho_log, encoding="utf-8")
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger, str(caminho_log)