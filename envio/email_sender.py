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
        log_callback=None,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = str(smtp_user or "").strip()
        self.smtp_password = (
            str(smtp_password or "").strip().replace(" ", "").replace("-", "")
        )
        self.remetente_nome = remetente_nome
        self.use_tls = use_tls
        self.log = log_callback or print

    def _montar_assunto(self, notas: List[NotaEnvio]) -> str:
        if len(notas) == 1:
            n = notas[0]
            return f"NFS-e - {n.cliente} - {n.especie}"
        cliente = notas[0].cliente if notas else "Cliente"
        return f"NFS-e(s) - {cliente} - {len(notas)} documento(s)"

    def _resumir_especies(self, notas: List[NotaEnvio]) -> str:
        especies = []
        vistos = set()

        for nota in notas:
            especie = str(getattr(nota, "especie", "") or "").strip()
            if not especie:
                continue
            chave = especie.lower()
            if chave in vistos:
                continue
            vistos.add(chave)
            especies.append(especie.upper())

        if not especies:
            return "SERVICOS"
        if len(especies) == 1:
            return especies[0]
        return " e ".join(especies)

    def _extrair_periodo(self, notas: List[NotaEnvio]) -> str:
        for nota in notas:
            mes = str(getattr(nota, "mes", "") or "").strip()
            if " - " in mes:
                mes = mes.split(" - ", 1)[1].strip()
            elif mes[:2].isdigit() and len(mes) > 3:
                mes = mes[3:].strip()

            if mes:
                return mes.upper()

            caminho_pdf = str(getattr(nota, "caminho_pdf", "") or "")
            partes = [p for p in caminho_pdf.replace("/", "\\").split("\\") if p]
            for parte in partes:
                texto = parte.strip()
                if len(texto) > 4 and texto[:2].isdigit() and " - " in texto:
                    return texto.split(" - ", 1)[1].strip().upper()

        return ""

    def montar_descricao_compartilhada(self, notas: List[NotaEnvio]) -> str:
        especies = self._resumir_especies(notas)
        periodo = self._extrair_periodo(notas)

        descricao = (
            f"Segue(m) em anexo a(s) nota(s) fiscal(is) de prestacao de servicos "
            f"referente a {especies}."
        )

        if periodo:
            descricao = f"{descricao} PERIODO: {periodo}."

        return descricao

    def _montar_corpo(self, notas: List[NotaEnvio]) -> str:
        primeira = notas[0]
        nome_contato = primeira.nome_contato or "Prezado(a)"

        linhas = []
        linhas.append(f"Ola {nome_contato},\n")
        linhas.append(f"{self.montar_descricao_compartilhada(notas)}\n")
        linhas.append("Detalhamento das notas:\n")

        for nota in notas:
            numero = getattr(nota, "numero_nfse", "") or "N/I"
            valor = getattr(nota, "valor", 0) or 0
            valor_formatado = (
                f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )
            linhas.append(f"- Nota N {numero} | Valor: R$ {valor_formatado}")

        linhas.append("\nCaso haja qualquer divergencia, por gentileza entrar em contato.\n")
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
                        with open(caminho, "rb") as arquivo:
                            dados = arquivo.read()

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
                            filename=nome_arquivo,
                        )
                        anexados += 1

            self.log(
                f"📧 Enviando email para {destino} com {len(notas)} nota(s) e {anexados} anexo(s)..."
            )

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            return ResultadoEnvio(
                sucesso=True,
                mensagem=f"E-mail enviado para {destino}",
                protocolo=f"EMAIL-{destino}",
            )
        except Exception as exc:
            return ResultadoEnvio(
                sucesso=False,
                mensagem=f"Erro ao enviar e-mail para {destino}: {exc}",
                protocolo="",
            )
