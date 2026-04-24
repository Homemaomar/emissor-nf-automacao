import ast
from pathlib import Path

from database.db import carregar_config, registrar_emissao_auditoria
from utils.logger_config import criar_logger_execucao
from envio import EnvioService

from automacao.emissor_nfse import EmissorNFSe


class OrquestradorEmissao:
    def __init__(
        self,
        leitor_planilha,
        atualizador_planilha,
        usuario=None,
        log_callback=None,
        progresso_callback=None,
        finish_callback=None,
        input_callback=None,
    ):
        self.leitor_planilha = leitor_planilha
        self.atualizador_planilha = atualizador_planilha
        self.usuario = usuario or {
            "id": None,
            "nome": "Sistema",
            "role": "sistema",
        }
        self.log_callback = log_callback
        self.progresso_callback = progresso_callback
        self.finish_callback = finish_callback
        self.input_callback = input_callback

    def _log(self, mensagem):
        if callable(self.log_callback):
            self.log_callback(mensagem)

    def _progresso(self, atual, total):
        if callable(self.progresso_callback):
            self.progresso_callback(atual, total)

    def _carregar_email_config_legacy(self):
        caminho_teste = Path("teste_envio.py")
        if not caminho_teste.exists():
            return "", ""

        try:
            source = caminho_teste.read_text(encoding="utf-8")
            modulo = ast.parse(source, filename=str(caminho_teste))
            for node in modulo.body:
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "email_config":
                        valor = ast.literal_eval(node.value)
                        if isinstance(valor, dict):
                            return (
                                str(valor.get("smtp_user", "") or "").strip(),
                                str(valor.get("smtp_password", "") or "").strip(),
                            )
        except Exception as exc:
            self._log(f"Nao foi possivel ler credenciais legadas de email: {exc}")

        return "", ""

    def _carregar_email_config(self):
        config = carregar_config()
        smtp_user = str(config.get("smtp_sender_email", "") or "").strip()
        smtp_password = str(config.get("smtp_sender_password", "") or "").strip()

        legacy_user, legacy_password = self._carregar_email_config_legacy()
        if not smtp_user:
            smtp_user = legacy_user
        if not smtp_password:
            smtp_password = legacy_password

        if not smtp_user or not smtp_password:
            return None

        return {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_user": smtp_user,
            "smtp_password": smtp_password,
            "remetente_nome": "Setor Fiscal",
            "use_tls": True,
        }

    def _executar_pos_emissao(self, caminho_planilha):
        email_config = self._carregar_email_config()

        service = EnvioService(
            caminho_planilha=caminho_planilha,
            nome_aba="NOTAS",
            email_config=email_config,
            log_callback=self._log,
            limite_por_minuto=30,
            max_tentativas=2,
        )
        service.processar_envios(
            enviar_email=True,
            enviar_whatsapp=True,
        )

    def executar(self, caminho_planilha, filtros, headless=False):
        logger, caminho_log = criar_logger_execucao(
            ano=filtros["ano"],
            mes=filtros["mes"].split(" - ")[0],
            municipio=filtros["municipio"],
        )

        self._log(f"Log da execucao: {caminho_log}")
        logger.info("===== INICIO DA EXECUCAO =====")
        logger.info("Usuario autenticado: %s", self.usuario.get("nome", "Sistema"))

        try:
            notas = self.leitor_planilha.listar_notas_pendentes(
                cliente=filtros.get("cliente"),
                especie=filtros.get("especie"),
                itens=filtros.get("itens"),
            )
        except Exception as exc:
            logger.error("Erro ao carregar planilha: %s", exc)
            self._log(f"Erro ao carregar planilha: {exc}")
            return {
                "status_final": "ERRO",
                "mensagem_final": "erro ao carregar planilha.",
            }

        if not notas:
            self._log("Nenhuma nota pendente encontrada.")
            logger.info("Nenhuma nota pendente encontrada.")
            return {
                "status_final": "SEM_NOTAS",
                "mensagem_final": "nenhuma nota pendente encontrada.",
            }

        total = len(notas)
        self._log(f"{total} nota(s) encontrada(s) para emissao.")
        logger.info("%s nota(s) encontrada(s) para emissao.", total)

        robo = EmissorNFSe(
            logger=logger,
            log_callback=lambda msg: self._log(str(msg)),
            input_callback=self.input_callback,
            caminho_base=caminho_planilha,
            pasta_saida_base=r"C:\Notas",
        )

        houve_erros = False
        houve_cancelamento = False
        houve_emitidas = False

        try:
            robo.preparar_sessao()

            itens = filtros.get("itens")
            if itens:
                itens_str = {str(i).strip() for i in itens}
                itens_planilha = {str(n["item"]).strip() for n in notas}
                itens_validos = itens_str.intersection(itens_planilha)
                itens_invalidos = itens_str - itens_validos

                if itens_invalidos:
                    self._log(
                        f"Itens invalidos ignorados: {sorted(list(itens_invalidos))}"
                    )

                if not itens_validos:
                    self._log("Nenhum item valido encontrado.")
                    return {
                        "status_final": "SEM_NOTAS",
                        "mensagem_final": "nenhum item valido encontrado.",
                    }

                notas = [
                    n for n in notas if str(n["item"]).strip() in itens_validos
                ]
                self._log(f"Itens selecionados: {sorted(list(itens_validos))}")

            for indice, linha in enumerate(notas, start=1):
                excel_row = int(linha["excel_row"])

                msg = f"Emitindo item {linha['item']}..."
                self._log(msg)
                logger.info(msg)

                descricao = str(linha.get("descricao") or "").replace("\n", " ").strip()
                dados_nota = {
                    "excel_row": excel_row,
                    "item": linha.get("item", ""),
                    "cliente": linha.get("cliente", ""),
                    "descricao": descricao,
                    "valor": round(float(linha.get("valor", 0) or 0), 2),
                    "ir": round(float(linha.get("ir", 0) or 0), 2),
                    "iss": round(float(linha.get("iss", 0) or 0), 2),
                    "cnpj": linha.get("cnpj", ""),
                    "ctn": linha.get("ctn", ""),
                    "nbs": linha.get("nbs", ""),
                    "email": linha.get("email", ""),
                    "especie": linha.get("especie", ""),
                }

                contexto = {
                    "ano": filtros["ano"],
                    "mes": filtros["mes"],
                    "municipio": filtros["municipio"],
                }

                try:
                    resultado = robo.emitir_nota(dados_nota, contexto)
                except Exception as exc:
                    logger.error("Erro critico no item %s: %s", dados_nota["item"], exc)
                    self._log(f"Erro critico no item {dados_nota['item']}: {exc}")
                    resultado = {
                        "status": "ERRO",
                        "numero_nfse": "",
                        "data_emissao": "",
                        "caminho_xml": "",
                        "caminho_pdf": "",
                        "mensagem": str(exc),
                    }

                status = resultado.get("status", "")
                numero_nfse = resultado.get("numero_nfse", "")
                mensagem = resultado.get("mensagem", "")

                if status == "ERRO":
                    houve_erros = True
                elif status == "CANCELADA":
                    houve_cancelamento = True
                    self._log("Lote interrompido por cancelamento do operador.")
                elif status == "EMITIDA":
                    houve_emitidas = True

                try:
                    self.atualizador_planilha.atualizar_resultado_emissao(
                        excel_row=excel_row,
                        status=status,
                        usuario=self.usuario.get("nome", "Sistema"),
                        numero_nfse=numero_nfse,
                        caminho_xml=resultado.get("caminho_xml", ""),
                        caminho_pdf=resultado.get("caminho_pdf", ""),
                        erro=mensagem,
                    )
                except Exception as exc:
                    logger.error("Erro ao atualizar planilha na linha %s: %s", excel_row, exc)
                    self._log(f"Falha ao atualizar planilha linha {excel_row}")

                try:
                    registrar_emissao_auditoria(
                        usuario=self.usuario,
                        item=dados_nota.get("item", ""),
                        status=status,
                        numero_nfse=numero_nfse,
                        caminho_planilha=caminho_planilha,
                        municipio=filtros.get("municipio", ""),
                        ano=filtros.get("ano", ""),
                        mes=filtros.get("mes", ""),
                        excel_row=excel_row,
                        mensagem=mensagem,
                    )
                except Exception as exc:
                    logger.error("Falha ao registrar auditoria da emissao: %s", exc)
                    self._log("Nao foi possivel registrar auditoria no banco.")

                self._progresso(indice, total)

                if status == "CANCELADA":
                    break

            if houve_emitidas:
                try:
                    self._log("Iniciando pos-emissao: email e WhatsApp.")
                    self._executar_pos_emissao(caminho_planilha)
                except Exception as exc:
                    houve_erros = True
                    logger.error("Falha no pos-emissao: %s", exc)
                    self._log(f"Falha no pos-emissao: {exc}")

            logger.info("===== FIM DA EXECUCAO =====")
            if houve_cancelamento:
                self._log("Execucao encerrada com cancelamento do operador.")
                return {
                    "status_final": "CANCELADA",
                    "mensagem_final": "lote cancelado pelo operador.",
                }

            if houve_erros:
                self._log("Execucao finalizada com pendencias.")
                return {
                    "status_final": "PENDENCIAS",
                    "mensagem_final": "lote finalizado com pendencias.",
                }

            self._log("Execucao finalizada com sucesso.")
            return {
                "status_final": "SUCESSO",
                "mensagem_final": "lote concluido com sucesso.",
            }

        finally:
            try:
                robo.fechar_driver()
            except Exception:
                pass

            if callable(self.finish_callback):
                self.finish_callback()
