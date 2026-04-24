import os
import time

import pandas as pd

from .agrupador import AgrupadorEnvio
from .atualizador_status import AtualizadorStatusEnvio
from .email_sender import EmailSender
from .whatsapp_sender import WhatsAppSender


class EnvioService:
    def __init__(
        self,
        caminho_planilha: str,
        nome_aba: str = "NOTAS",
        email_config: dict = None,
        log_callback=None,
        limite_por_minuto: int = 20,
        max_tentativas: int = 3,
    ):
        self.caminho_planilha = caminho_planilha
        self.nome_aba = nome_aba
        self.log = log_callback or print
        self.limite_por_minuto = limite_por_minuto
        self.max_tentativas = max_tentativas

        self.agrupador = AgrupadorEnvio(log_callback=self.log)
        self.atualizador = AtualizadorStatusEnvio(
            caminho_planilha=caminho_planilha,
            nome_aba=nome_aba,
            log_callback=self.log,
        )

        self.email_sender = None
        if email_config:
            self.email_sender = EmailSender(
                smtp_host=email_config["smtp_host"],
                smtp_port=email_config["smtp_port"],
                smtp_user=email_config["smtp_user"],
                smtp_password=email_config["smtp_password"],
                remetente_nome=email_config.get("remetente_nome", "Setor Fiscal"),
                use_tls=email_config.get("use_tls", True),
                log_callback=self.log,
            )

        self.whatsapp_sender = WhatsAppSender(log_callback=self.log)

    def _carregar_df(self):
        if not os.path.exists(self.caminho_planilha):
            raise Exception(f"Planilha nao encontrada: {self.caminho_planilha}")

        self.log(f"Carregando planilha: {self.caminho_planilha}")

        xls = pd.ExcelFile(self.caminho_planilha, engine="openpyxl")

        try:
            abas = xls.sheet_names
            abas_normalizadas = [aba.upper().strip() for aba in abas]

            if "NOTAS" in abas_normalizadas:
                nome_real = abas[abas_normalizadas.index("NOTAS")]
            else:
                raise Exception(f"Aba NOTAS nao encontrada. Abas disponiveis: {abas}")

            df = pd.read_excel(
                self.caminho_planilha,
                sheet_name=nome_real,
                engine="openpyxl",
                dtype=str,
            )
        finally:
            xls.close()

        df.columns = [col.strip().upper() for col in df.columns]

        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()

        df = df.fillna("")

        self.log("Colunas carregadas:")
        self.log(list(df.columns))
        self.log(f"Total de registros: {len(df)}")

        return df

    def _aplicar_limite(self):
        if self.limite_por_minuto <= 0:
            return

        pausa = max(1, int(60 / self.limite_por_minuto))
        self.log(f"Aguardando {pausa}s para controle de taxa...")
        time.sleep(pausa)

    def _montar_mensagem_whatsapp(self, notas_grupo):
        descricao_compartilhada = "segue sua(s) nota(s) fiscal(is) em anexo."
        if self.email_sender:
            descricao_compartilhada = self.email_sender.montar_descricao_compartilhada(
                notas_grupo
            )

        return descricao_compartilhada

    def processar_envios(self, enviar_email=True, enviar_whatsapp=True):
        self.log("INICIANDO MODULO DE ENVIO...")

        df = self._carregar_df()
        notas = self.agrupador.filtrar_notas_enviaveis(df)

        grupos_email = self.agrupador.agrupar_por_email(notas) if enviar_email else {}
        grupos_whatsapp = (
            self.agrupador.agrupar_por_whatsapp(notas) if enviar_whatsapp else {}
        )

        if enviar_email and not self.email_sender:
            self.log("Configuracao de email nao informada. Envio por email ignorado.")
            grupos_email = {}

        whatsapp = None
        if enviar_whatsapp and grupos_whatsapp:
            whatsapp = self.whatsapp_sender
            whatsapp.iniciar()

        for destino, notas_grupo in grupos_email.items():
            linhas = [n.linha_excel for n in notas_grupo]
            resultado = None

            for tentativa in range(1, self.max_tentativas + 1):
                self.log(f"Tentativa {tentativa}/{self.max_tentativas} para {destino}")
                resultado = self.email_sender.enviar_email(destino, notas_grupo)

                if resultado.sucesso:
                    self.atualizador.atualizar_status_email(
                        linhas_excel=linhas,
                        status="ENVIADO",
                        erro="",
                        protocolo=resultado.protocolo,
                    )
                    break

                self.log(resultado.mensagem)

            if resultado and not resultado.sucesso:
                self.atualizador.atualizar_status_email(
                    linhas_excel=linhas,
                    status="ERRO",
                    erro=resultado.mensagem,
                    protocolo="",
                )

            self._aplicar_limite()

        for numero, notas_grupo in grupos_whatsapp.items():
            linhas = [n.linha_excel for n in notas_grupo]

            try:
                self.log(
                    f"Enviando WhatsApp para {numero} com {len(notas_grupo)} nota(s)..."
                )

                mensagem = self._montar_mensagem_whatsapp(notas_grupo)

                sucesso_msg = whatsapp.enviar(numero, mensagem)
                if not sucesso_msg:
                    raise Exception("Falha ao enviar mensagem inicial")

                time.sleep(2)

                arquivos = [n.caminho_pdf for n in notas_grupo if n.caminho_pdf]
                self.log(f"Enviando {len(arquivos)} arquivo(s) em lote")

                sucesso_arq = whatsapp.enviar_multiplos_arquivos(arquivos)
                if not sucesso_arq:
                    raise Exception("Erro no envio em lote")

                self.atualizador.atualizar_status_whatsapp(
                    linhas_excel=linhas,
                    status="ENVIADO",
                    erro="",
                    protocolo="WHATSAPP_OK",
                )

            except Exception as exc:
                self.log(f"Erro ao enviar WhatsApp para {numero}: {exc}")
                self.atualizador.atualizar_status_whatsapp(
                    linhas_excel=linhas,
                    status="ERRO",
                    erro=str(exc),
                    protocolo="",
                )

            self._aplicar_limite()

        self.log("PROCESSAMENTO DE ENVIO FINALIZADO.")

    def calcular_indicadores(df):
        total_pendentes = df[df["STATUS"] == "PENDENTE"].shape[0]
        total_emitidas = df[df["STATUS"] == "EMITIDA"].shape[0]
        valor_total = df[df["STATUS"] == "EMITIDA"]["VALOR"].sum()

        return {
            "pendentes": int(total_pendentes),
            "emitidas": int(total_emitidas),
            "valor_total": float(valor_total),
        }
