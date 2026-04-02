import os
import smtplib
from email.message import EmailMessage
from typing import List

from .modelos import NotaEnvio, ResultadoEnvio


class EmailSender:
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        remetente_nome: str = "Setor Fiscal",
        use_tls: bool = True,
        log_callback=None
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.remetente_nome = remetente_nome
        self.use_tls = use_tls
        self.log = log_callback or print

    def _montar_assunto(self, notas: List[NotaEnvio]) -> str:
        if len(notas) == 1:
            n = notas[0]
            return f"NFS-e - {n.cliente} - {n.especie}"
        cliente = notas[0].cliente if notas else "Cliente"
        return f"NFS-e(s) - {cliente} - {len(notas)} documento(s)"

    def _montar_corpo(self, notas: List[NotaEnvio]) -> str:

        primeira = notas[0]

        nome_contato = primeira.nome_contato or "Prezado(a)"
        especie = primeira.especie or "serviços"
        municipio = getattr(primeira, "municipio", "")
        
        # tenta extrair mês/ano da data_emissao (se existir)
        data = getattr(primeira, "data_emissao", "")
        mes = ""
        ano = ""

        if data and "/" in data:
            try:
                partes = data.split("/")
                mes = partes[1]
                ano = partes[2]
            except:
                pass

        linhas = []

        # Saudação
        linhas.append(f"Olá {nome_contato},\n")

        # Introdução profissional
        linhas.append(
            f"Segue(m) em anexo a(s) nota(s) fiscal(is) de prestação de serviços "
            f"referente a {especie}, do período {mes}/{ano}, "
            f"do município de {municipio}.\n"
        )

        # Detalhamento
        linhas.append("Detalhamento das notas:\n")

        for nota in notas:
            numero = getattr(nota, "numero_nfse", "") or "N/I"
            valor = getattr(nota, "valor", 0) or 0

            valor_formatado = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

            linhas.append(f"• Nota Nº {numero} | Valor: R$ {valor_formatado}")

        # Complemento
        linhas.append("\nCaso haja qualquer divergência, por gentileza entrar em contato.\n")

        # Rodapé
        linhas.append("Atenciosamente,")
        linhas.append(self.remetente_nome)

        return "\n".join(linhas)

    def enviar_email(self, destino: str, notas: List[NotaEnvio]) -> ResultadoEnvio:
        try:
            msg = EmailMessage()
            msg["Subject"] = self._montar_assunto(notas)
            msg["From"] = f"{self.remetente_nome} <{self.smtp_user}>"
            msg["To"] = destino
            msg.set_content(self._montar_corpo(notas))

            anexados = 0

            for nota in notas:
                for caminho in [nota.caminho_pdf, nota.caminho_xml]:
                    if caminho and os.path.exists(caminho):
                        with open(caminho, "rb") as f:
                            dados = f.read()

                        nome_arquivo = os.path.basename(caminho)
                        maintype = "application"
                        subtype = "octet-stream"

                        if nome_arquivo.lower().endswith(".pdf"):
                            subtype = "pdf"
                        elif nome_arquivo.lower().endswith(".xml"):
                            subtype = "xml"

                        msg.add_attachment(
                            dados,
                            maintype=maintype,
                            subtype=subtype,
                            filename=nome_arquivo
                        )
                        anexados += 1

            self.log(f"📧 Enviando email para {destino} com {len(notas)} nota(s) e {anexados} anexo(s)...")

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            return ResultadoEnvio(
                sucesso=True,
                mensagem=f"E-mail enviado para {destino}",
                protocolo=f"EMAIL-{destino}"
            )

        except Exception as e:
            return ResultadoEnvio(
                sucesso=False,
                mensagem=f"Erro ao enviar e-mail para {destino}: {e}",
                protocolo=""
            )