import time
import os
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
        max_tentativas: int = 3
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
            log_callback=self.log
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
                log_callback=self.log
            )

        self.whatsapp_sender = WhatsAppSender(log_callback=self.log)

    def _carregar_df(self):


        if not os.path.exists(self.caminho_planilha):
            raise Exception(f"Planilha não encontrada: {self.caminho_planilha}")

        xls = pd.ExcelFile(self.caminho_planilha, engine="openpyxl")

        try:
            abas = xls.sheet_names
            abas_normalizadas = [a.upper().strip() for a in abas]

            if "NOTAS" in abas_normalizadas:
                nome_real = abas[abas_normalizadas.index("NOTAS")]
            else:
                raise Exception(f"Aba NOTAS não encontrada. Abas disponíveis: {abas}")

            df = pd.read_excel(
                self.caminho_planilha,
                sheet_name=nome_real,
                engine="openpyxl",
                dtype=str
            )

            return df

        finally:
            xls.close()  # 🔥 ISSO REMOVE O ERRO

        # ==========================================
        # 3. LER COMO STRING (REMOVE .0 DO TELEFONE)
        # ==========================================
        df = pd.read_excel(
            self.caminho_planilha,
            sheet_name=nome_real,
            engine="openpyxl",
            dtype=str  # 🔥 ESSENCIAL
        )

        # ==========================================
        # 4. NORMALIZAR COLUNAS
        # ==========================================
        df.columns = [c.strip().upper() for c in df.columns]

        # ==========================================
        # 5. LIMPAR DADOS (STRING)
        # ==========================================
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()

        # ==========================================
        # 6. TRATAR VALORES NAN
        # ==========================================
        df = df.fillna("")

        # ==========================================
        # 7. DEBUG OPCIONAL
        # ==========================================
        self.log("📊 Colunas carregadas:")
        self.log(list(df.columns))

        self.log(f"📄 Total de registros: {len(df)}")

        return df

    def _aplicar_limite(self):
        if self.limite_por_minuto <= 0:
            return

        pausa = max(1, int(60 / self.limite_por_minuto))
        self.log(f"⏱️ Aguardando {pausa}s para controle de taxa...")
        time.sleep(pausa)

    def processar_envios(self, enviar_email=True, enviar_whatsapp=True):
        self.log("🚀 INICIANDO MÓDULO DE ENVIO...")

        df = self._carregar_df()

        notas = self.agrupador.filtrar_notas_enviaveis(df)

        grupos_email = self.agrupador.agrupar_por_email(notas) if enviar_email else {}
        grupos_whatsapp = self.agrupador.agrupar_por_whatsapp(notas) if enviar_whatsapp else {}

        if enviar_email and not self.email_sender:
            self.log("⚠️ Configuração de email não informada. Envio por email ignorado.")
            grupos_email = {}

        # ==========================
        # INICIAR WHATSAPP (UMA VEZ)
        # ==========================
        whatsapp = None

        if enviar_whatsapp and grupos_whatsapp:
            from .whatsapp_sender import WhatsAppSender
            whatsapp = WhatsAppSender(log_callback=self.log)
            whatsapp.iniciar()

        # ==========================
        # ENVIO POR EMAIL
        # ==========================
        for destino, notas_grupo in grupos_email.items():
            linhas = [n.linha_excel for n in notas_grupo]

            resultado = None
            for tentativa in range(1, self.max_tentativas + 1):
                self.log(f"📧 Tentativa {tentativa}/{self.max_tentativas} para {destino}")
                resultado = self.email_sender.enviar_email(destino, notas_grupo)

                if resultado.sucesso:
                    self.atualizador.atualizar_status_email(
                        linhas_excel=linhas,
                        status="ENVIADO",
                        erro="",
                        protocolo=resultado.protocolo
                    )
                    break
                else:
                    self.log(f"❌ {resultado.mensagem}")

            if resultado and not resultado.sucesso:
                self.atualizador.atualizar_status_email(
                    linhas_excel=linhas,
                    status="ERRO",
                    erro=resultado.mensagem,
                    protocolo=""
                )

            self._aplicar_limite()

        # ==========================
        # ENVIO POR WHATSAPP (REFATORADO)
        # ==========================
        for numero, notas_grupo in grupos_whatsapp.items():
            linhas = [n.linha_excel for n in notas_grupo]

            try:
                self.log(f"📱 Enviando WhatsApp para {numero} com {len(notas_grupo)} nota(s)...")
                self.log(f"DEBUG NUMERO RAW: {numero} | tipo: {type(numero)}")
                nome = notas_grupo[0].nome_contato or "Cliente"

                mensagem = f"Olá {nome}, segue sua(s) nota(s) fiscal(is) em anexo."

                # ==========================================
                # 1. ABRIR CONVERSA + ENVIAR MENSAGEM
                # ==========================================
                sucesso_msg = whatsapp.enviar(numero, mensagem)

                if not sucesso_msg:
                    raise Exception("Falha ao enviar mensagem inicial")

                time.sleep(2)

                # ==========================================
                # 2. ENVIAR TODOS OS PDFs NA MESMA CONVERSA
                # ==========================================
                for nota in notas_grupo:

                    if not nota.caminho_pdf:
                        continue

                    self.log(f"📎 Enviando arquivo: {nota.caminho_pdf}")

                    sucesso_arq = whatsapp.enviar_arquivo(nota.caminho_pdf)

                    if not sucesso_arq:
                        raise Exception(f"Erro ao enviar arquivo: {nota.caminho_pdf}")

                    time.sleep(2)

                # ==========================================
                # 3. ATUALIZAR STATUS
                # ==========================================
                self.atualizador.atualizar_status_whatsapp(
                    linhas_excel=linhas,
                    status="ENVIADO",
                    erro="",
                    protocolo="WHATSAPP_OK"
                )

            except Exception as e:
                self.log(f"❌ Erro ao enviar WhatsApp para {numero}: {e}")

                self.atualizador.atualizar_status_whatsapp(
                    linhas_excel=linhas,
                    status="ERRO",
                    erro=str(e),
                    protocolo=""
                )

            self._aplicar_limite()

        self.log("✅ PROCESSAMENTO DE ENVIO FINALIZADO.")