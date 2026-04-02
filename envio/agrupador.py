from collections import defaultdict
from typing import List, Dict

from .modelos import NotaEnvio
from .utils_envio import (
    normalizar_texto,
    normalizar_status,
    normalizar_tipo_envio,
    normalizar_flag_sim_nao,
    arquivo_existe,
)


class AgrupadorEnvio:
    def __init__(self, log_callback=None):
        self.log = log_callback or print

    def filtrar_notas_enviaveis(self, df) -> List[NotaEnvio]:
        notas = []

        colunas = [c.strip().upper() for c in df.columns]
        mapa_colunas = {
            col.strip().upper(): col
            for col in df.columns
        }

        obrigatorias = [
            "ITEM", "CLIENTE", "SECRETARIA", "VALOR", "ESPECIE",
            "EMAIL", "NOME_CONTATO", "WHATSAPP",
            "STATUS", "STATUS_EMAIL", "STATUS_WHATSAPP",
            "CAMINHO_PDF", "CAMINHO_XML"
        ]

        for col in obrigatorias:
            if col not in colunas:
                raise Exception(f"Coluna obrigatória não encontrada: {col}")

        for idx, row in df.iterrows():
            status = normalizar_status(row[mapa_colunas["STATUS"]], "")
            status_email = normalizar_status(row[mapa_colunas["STATUS_EMAIL"]], "PENDENTE")
            status_whatsapp = normalizar_status(row[mapa_colunas["STATUS_WHATSAPP"]], "PENDENTE")

            tipo_envio = "AMBOS"
            enviar_automatico = "SIM"

            if "TIPO_ENVIO" in mapa_colunas:
                tipo_envio = normalizar_tipo_envio(row[mapa_colunas["TIPO_ENVIO"]])

            if "ENVIAR_AUTOMATICO" in mapa_colunas:
                enviar_automatico = normalizar_flag_sim_nao(row[mapa_colunas["ENVIAR_AUTOMATICO"]])

            if status != "EMITIDA":
                continue

            if enviar_automatico != "SIM":
                continue

            pdf = normalizar_texto(row[mapa_colunas["CAMINHO_PDF"]])
            xml = normalizar_texto(row[mapa_colunas["CAMINHO_XML"]])

            item = normalizar_texto(row[mapa_colunas["ITEM"]])

            if not arquivo_existe(pdf):
                self.log(f"⚠️ ITEM {item}: PDF inválido → ignorado")
                continue

            if not arquivo_existe(xml):
                self.log(f"⚠️ ITEM {item}: XML inválido → ignorado")
                continue

            nota = NotaEnvio(
                linha_excel=idx + 2,
                item=normalizar_texto(row[mapa_colunas["ITEM"]]),
                cliente=normalizar_texto(row[mapa_colunas["CLIENTE"]]),
                secretaria=normalizar_texto(row[mapa_colunas["SECRETARIA"]]),
                valor=float(row[mapa_colunas["VALOR"]]) if str(row[mapa_colunas["VALOR"]]).strip() else 0.0,
                especie=normalizar_texto(row[mapa_colunas["ESPECIE"]]),
                email=normalizar_texto(row[mapa_colunas["EMAIL"]]),
                nome_contato=normalizar_texto(row[mapa_colunas["NOME_CONTATO"]]),
                whatsapp=normalizar_texto(row[mapa_colunas["WHATSAPP"]]),
                status=status,
                status_email=status_email,
                status_whatsapp=status_whatsapp,
                caminho_pdf=pdf,
                caminho_xml=xml,
                tipo_envio=tipo_envio,
                enviar_automatico=enviar_automatico
            )

            if not arquivo_existe(pdf):
                self.log(f"⚠️ ITEM {nota.item}: PDF não encontrado: {pdf}")

            if not arquivo_existe(xml):
                self.log(f"⚠️ ITEM {nota.item}: XML não encontrado: {xml}")

            notas.append(nota)

        self.log(f"📦 {len(notas)} nota(s) apta(s) para análise de envio.")
        return notas

    def agrupar_por_email(self, notas: List[NotaEnvio]) -> Dict[str, List[NotaEnvio]]:
        grupos = defaultdict(list)

        for nota in notas:
            if nota.tipo_envio not in ("EMAIL", "AMBOS"):
                continue
            if nota.status_email != "PENDENTE":
                continue
            email = nota.email.strip()

            if not email or email.lower() in ["nan", "none", ""]:
                self.log(f"⚠️ ITEM {nota.item}: sem e-mail → ignorado")
                continue

            grupos[nota.email].append(nota)

        self.log(f"📧 {len(grupos)} grupo(s) de e-mail montado(s).")
        return dict(grupos)

    def agrupar_por_whatsapp(self, notas: List[NotaEnvio]) -> Dict[str, List[NotaEnvio]]:
        grupos = defaultdict(list)

        for nota in notas:
            if nota.tipo_envio not in ("WHATSAPP", "AMBOS"):
                continue
            if nota.status_whatsapp != "PENDENTE":
                continue
                whatsapp = nota.whatsapp.strip()

                if not whatsapp or whatsapp.lower() in ["nan", "none", ""]:
                    self.log(f"⚠️ ITEM {nota.item}: sem WhatsApp → ignorado")
                    continue

            grupos[nota.whatsapp].append(nota)

        self.log(f"📱 {len(grupos)} grupo(s) de WhatsApp montado(s).")
        return dict(grupos)