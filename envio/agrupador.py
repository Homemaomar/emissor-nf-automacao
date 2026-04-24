from .modelos import NotaEnvio
from .utils_envio import (
    arquivo_existe,
    normalizar_flag_sim_nao,
    normalizar_status,
    normalizar_texto,
    normalizar_tipo_envio,
)


class AgrupadorEnvio:
    def __init__(self, log_callback=None):
        self.log = log_callback or print

    def _obter_valor(self, row, mapa_colunas, *nomes, default=""):
        for nome in nomes:
            chave = str(nome or "").strip().upper()
            coluna_real = mapa_colunas.get(chave)
            if coluna_real:
                return row[coluna_real]
        return default

    def _propagar_canais_contato(self, notas):
        email_por_chave = {}
        whatsapp_por_chave = {}
        nome_por_chave = {}

        def chaves_nota(nota):
            return [
                f"cliente:{(nota.cliente or '').strip().lower()}",
                f"secretaria:{(nota.secretaria or '').strip().lower()}",
                f"whatsapp:{(nota.whatsapp or '').strip()}",
            ]

        for nota in notas:
            for chave in chaves_nota(nota):
                if chave.endswith(":"):
                    continue
                if nota.email and chave not in email_por_chave:
                    email_por_chave[chave] = nota.email
                if nota.whatsapp and chave not in whatsapp_por_chave:
                    whatsapp_por_chave[chave] = nota.whatsapp
                if nota.nome_contato and chave not in nome_por_chave:
                    nome_por_chave[chave] = nota.nome_contato

        for nota in notas:
            for chave in chaves_nota(nota):
                if not nota.email and chave in email_por_chave:
                    nota.email = email_por_chave[chave]
                if not nota.whatsapp and chave in whatsapp_por_chave:
                    nota.whatsapp = whatsapp_por_chave[chave]
                if not nota.nome_contato and chave in nome_por_chave:
                    nota.nome_contato = nome_por_chave[chave]

        return notas

    def filtrar_notas_enviaveis(self, df):
        notas = []

        colunas = [c.strip().upper() for c in df.columns]
        mapa_colunas = {col.strip().upper(): col for col in df.columns}

        obrigatorias = ["ITEM", "VALOR", "STATUS", "CAMINHO_PDF"]
        for col in obrigatorias:
            if col not in colunas:
                raise Exception(f"Coluna obrigatoria nao encontrada: {col}")

        for idx, row in df.iterrows():
            status = normalizar_status(
                self._obter_valor(row, mapa_colunas, "STATUS"),
                "",
            )
            status_email = normalizar_status(
                self._obter_valor(row, mapa_colunas, "STATUS_EMAIL", default="PENDENTE"),
                "PENDENTE",
            )
            status_whatsapp = normalizar_status(
                self._obter_valor(row, mapa_colunas, "STATUS_WHATSAPP", default="PENDENTE"),
                "PENDENTE",
            )

            tipo_envio = "AMBOS"
            enviar_automatico = "SIM"

            if "TIPO_ENVIO" in mapa_colunas:
                tipo_envio = normalizar_tipo_envio(
                    self._obter_valor(row, mapa_colunas, "TIPO_ENVIO")
                )

            if "ENVIAR_AUTOMATICO" in mapa_colunas:
                enviar_automatico = normalizar_flag_sim_nao(
                    self._obter_valor(row, mapa_colunas, "ENVIAR_AUTOMATICO")
                )

            if status != "EMITIDA":
                continue

            if enviar_automatico != "SIM":
                continue

            pdf = normalizar_texto(
                self._obter_valor(row, mapa_colunas, "CAMINHO_PDF")
            )
            xml = normalizar_texto(
                self._obter_valor(row, mapa_colunas, "CAMINHO_XML")
            )
            item = normalizar_texto(
                self._obter_valor(row, mapa_colunas, "ITEM")
            )

            if not arquivo_existe(pdf):
                self.log(f"ITEM {item}: PDF invalido -> ignorado")
                continue

            if not arquivo_existe(xml):
                self.log(f"ITEM {item}: XML nao encontrado (opcional)")

            nota = NotaEnvio(
                linha_excel=idx + 2,
                item=item,
                cliente=normalizar_texto(
                    self._obter_valor(row, mapa_colunas, "CLIENTE", "SECRETARIA")
                ),
                secretaria=normalizar_texto(
                    self._obter_valor(row, mapa_colunas, "SECRETARIA", "CLIENTE")
                ),
                valor=float(
                    self._obter_valor(row, mapa_colunas, "VALOR", default=0) or 0
                ),
                especie=normalizar_texto(
                    self._obter_valor(row, mapa_colunas, "ESPECIE", "ESPÉCIE")
                ),
                email=normalizar_texto(
                    self._obter_valor(row, mapa_colunas, "EMAIL")
                ).lower().strip(),
                nome_contato=normalizar_texto(
                    self._obter_valor(
                        row, mapa_colunas, "NOME_CONTATO", "CLIENTE", "SECRETARIA"
                    )
                ),
                whatsapp=self._normalizar_whatsapp(
                    self._obter_valor(row, mapa_colunas, "WHATSAPP")
                ),
                status=status,
                status_email=status_email,
                status_whatsapp=status_whatsapp,
                caminho_pdf=pdf,
                caminho_xml=xml,
                tipo_envio=tipo_envio,
                enviar_automatico=enviar_automatico,
            )
            notas.append(nota)

        notas = self._propagar_canais_contato(notas)
        self.log(f"{len(notas)} nota(s) apta(s) para envio.")
        return notas

    def agrupar_por_email(self, notas):
        grupos = {}

        for nota in notas:
            if nota.tipo_envio == "WHATSAPP":
                continue

            if normalizar_status(nota.status_email, "PENDENTE") == "ENVIADO":
                continue

            email = (nota.email or "").strip().lower()
            if not email:
                self.log(f"ITEM {nota.item}: sem e-mail -> ignorado no EMAIL")
                continue

            grupos.setdefault(email, []).append(nota)

        self.log(f"{len(grupos)} grupo(s) de e-mail montado(s).")
        return grupos

    def agrupar_por_whatsapp(self, notas):
        grupos = {}

        for nota in notas:
            if nota.tipo_envio == "EMAIL":
                continue

            if normalizar_status(nota.status_whatsapp, "PENDENTE") == "ENVIADO":
                continue

            numero = (nota.whatsapp or "").strip()
            if not numero:
                self.log(f"ITEM {nota.item}: sem WhatsApp -> ignorado no WHATSAPP")
                continue

            grupos.setdefault(numero, []).append(nota)

        self.log(f"{len(grupos)} grupo(s) de WhatsApp montado(s).")
        return grupos

    def _normalizar_whatsapp(self, numero):
        if not numero:
            return ""

        numero = str(numero).strip()
        numero = "".join(c for c in numero if c.isdigit())

        if numero.startswith("55"):
            return numero

        if len(numero) >= 10:
            return "55" + numero

        return numero
