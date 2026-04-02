import time
import pandas as pd
from automacao.emissor_nfse import EmissorNFSe
from utils.logger_config import criar_logger_execucao

import automacao.emissor_nfse

print("ARQUIVO CARREGADO:", automacao.emissor_nfse.__file__)
print("TEM EmissorNFSe?", hasattr(automacao.emissor_nfse, "EmissorNFSe"))


class OrquestradorEmissao:
    print("🔥 ARQUIVO CERTO CARREGADO")

    def __init__(
        self,
        leitor_planilha,
        atualizador_planilha,
        log_callback=None,
        progresso_callback=None,
        finish_callback=None
    ):
        self.leitor_planilha = leitor_planilha
        self.atualizador_planilha = atualizador_planilha
        self.log_callback = log_callback
        self.progresso_callback = progresso_callback
        self.finish_callback = finish_callback

    # ===============================
    # HELPERS
    # ===============================
    def _log(self, mensagem: str):
        if callable(self.log_callback):
            self.log_callback(mensagem)

    def _progresso(self, atual: int, total: int):
        if callable(self.progresso_callback):
            self.progresso_callback(atual, total)

    # ===============================
    # EXECUÇÃO
    # ===============================
    def executar(self, caminho_planilha: str, filtros: dict, headless: bool = False):

        # ===============================
        # CRIAR LOGGER (CORRETO)
        # ===============================
        logger, caminho_log = criar_logger_execucao(
            ano=filtros["ano"],
            mes=filtros["mes"].split(" - ")[0],
            municipio=filtros["municipio"]
        )

        if not hasattr(logger, "info"):
            raise Exception(f"Logger inválido: {type(logger)}")

        self._log(f"📄 Log da execução: {caminho_log}")
        logger.info("===== INÍCIO DA EXECUÇÃO =====")

        print("DEBUG LOGGER:", logger)
        print("TIPO LOGGER:", type(logger))

        # ===============================
        # CARREGAR DADOS
        # ===============================
        try:
            notas = self.leitor_planilha.listar_notas_pendentes(
                secretaria=filtros.get("secretaria"),
                especie=filtros.get("especie"),
                itens=[filtros.get("item")] if filtros.get("item") else None
            )
        except Exception as e:
            logger.error(f"Erro ao carregar planilha: {e}")
            self._log(f"❌ Erro ao carregar planilha: {e}")
            return

        if not notas:
            self._log("⚠ Nenhuma nota pendente encontrada.")
            logger.info("Nenhuma nota pendente encontrada.")
            return

        total = len(notas)
        self._log(f"🔎 {total} nota(s) encontrada(s) para emissão.")
        logger.info(f"{total} nota(s) encontrada(s) para emissão.")

        # ===============================
        # INICIAR ROBÔ
        # ===============================
        robo = EmissorNFSe(
            logger=logger,
            log_callback=lambda msg: print(msg),
            caminho_base=caminho_planilha,
            pasta_saida_base=r"C:\Notas"
        )

        try:
            robo.preparar_sessao()

            # ===============================
            # LOOP PRINCIPAL
            # ===============================
            for indice, linha in enumerate(notas, start=1):

                excel_row = int(linha["excel_row"])

                msg = f"🚀 Emitindo ITEM {linha['item']}..."
                self._log(msg)
                logger.info(msg)

                valor_desc = linha.get("descricao") or ""
                descricao = str(valor_desc).replace("\n", " ").strip()

                dados_nota = {
                    "excel_row": excel_row,
                    "item": linha.get("item", ""),
                    "descricao": descricao,
                    "valor": round(float(linha.get("valor", 0) or 0), 2),
                    "ir": round(float(linha.get("ir", 0) or 0), 2),
                    "iss": round(float(linha.get("iss", 0) or 0), 2),
                    "cnpj": linha.get("cnpj", ""),
                    "ctn": linha.get("ctn", ""),
                    "nbs": linha.get("nbs", ""),
                    "email": linha.get("email", ""),
                }

                contexto = {
                    "ano": filtros["ano"],
                    "mes": filtros["mes"],
                    "municipio": filtros["municipio"],
                }

                # ===============================
                # EMISSÃO
                # ===============================
                try:
                    resultado = robo.emitir_nota(dados_nota, contexto)
                except Exception as e:
                    logger.error(f"Erro crítico no ITEM {dados_nota['item']}: {e}")
                    self._log(f"❌ Erro crítico no ITEM {dados_nota['item']}: {e}")

                    resultado = {
                        "status": "ERRO",
                        "numero_nfse": "",
                        "data_emissao": "",
                        "caminho_xml": "",
                        "caminho_pdf": "",
                        "mensagem": str(e),
                    }

                # ===============================
                # ATUALIZAR PLANILHA
                # ===============================
                try:
                    self.atualizador_planilha.atualizar_resultado_emissao(
                        excel_row=excel_row,
                        status=resultado.get("status", ""),
                        usuario="Sistema",
                        numero_nfse=resultado.get("numero_nfse", ""),
                        caminho_xml=resultado.get("caminho_xml", ""),
                        caminho_pdf=resultado.get("caminho_pdf", ""),
                        erro=resultado.get("mensagem", "")
                    )
                except Exception as e:
                    logger.error(f"Erro ao atualizar planilha (linha {excel_row}): {e}")
                    self._log(f"⚠ Falha ao atualizar planilha linha {excel_row}")

                self._progresso(indice, total)

            # ===============================
            # FINALIZA EXECUÇÃO
            # ===============================
            logger.info("===== FIM DA EXECUÇÃO =====")
            self._log("✅ Execução finalizada com sucesso.")

            # ===============================
            # ENVIO DE NOTAS (B)
            # ===============================
            from envio import EnvioService

            def perguntar_envio():
                print("\n==============================")
                print("📤 ENVIO DE NOTAS")
                print("==============================")
                print("Deseja enviar as notas emitidas agora?")
                print("1 - Sim")
                print("2 - Não")

                while True:
                    opcao = input("Digite: ").strip()
                    if opcao == "1":
                        return True
                    elif opcao == "2":
                        return False

                    print("Opção inválida")

            if perguntar_envio():

                self._log("📤 Iniciando envio das notas...")

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
                    log_callback=lambda msg: self._log(msg),
                    limite_por_minuto=10,
                    max_tentativas=3
                )

                service.processar_envios(
                    enviar_email=True,
                    enviar_whatsapp=True
                )

            else:
                self._log("ℹ️ Envio ignorado pelo usuário.")

        finally:
            try:
                robo.fechar_driver()
            except Exception:
                pass

            if callable(self.finish_callback):
                self.finish_callback()
