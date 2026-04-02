import os
import time
import traceback
from functools import wraps

from automacao.excecoes import EtapaErro


def etapa_automacao(nome_etapa: str, tentativas: int = 3, espera_segundos: int = 2):
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            ultima_excecao = None

            for tentativa in range(1, tentativas + 1):
                try:
                    self.logger.info(f"[{nome_etapa}] Iniciando tentativa {tentativa}/{tentativas}")
                    self._log(f"[{nome_etapa}] Iniciando tentativa {tentativa}/{tentativas}")

                    inicio = time.time()
                    resultado = func(self, *args, **kwargs)
                    fim = time.time()

                    self.logger.info(f"[{nome_etapa}] Sucesso em {fim - inicio:.2f}s")
                    self._log(f"[{nome_etapa}] Sucesso")

                    return resultado

                except Exception as e:
                    ultima_excecao = e

                    self.logger.error(f"[{nome_etapa}] Erro na tentativa {tentativa}: {repr(e)}")
                    self.logger.error(traceback.format_exc())
                    self._log(f"[{nome_etapa}] Erro: {str(e)}")

                    try:
                        self._salvar_evidencias(nome_etapa, tentativa)
                    except Exception as evidencia_erro:
                        self.logger.error(f"Falha ao salvar evidências: {evidencia_erro}")

                    if tentativa < tentativas:
                        time.sleep(espera_segundos)
                        self._tentar_recuperar_estado()
                    else:
                        raise EtapaErro(nome_etapa, str(e), e) from e

            raise EtapaErro(nome_etapa, str(ultima_excecao), ultima_excecao)

        return wrapper
    return decorator