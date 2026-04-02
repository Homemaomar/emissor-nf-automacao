class AutomacaoErro(Exception):
    """Erro base da automação."""
    pass


class EtapaErro(AutomacaoErro):
    """Erro em uma etapa específica do processo."""

    def __init__(self, etapa: str, mensagem: str, original_exception: Exception = None):
        self.etapa = etapa
        self.mensagem = mensagem
        self.original_exception = original_exception
        super().__init__(f"[{etapa}] {mensagem}")


class EmissaoNaoAutorizadaErro(AutomacaoErro):
    """Quando a emissão não pode prosseguir por bloqueio do site."""
    pass


class NotaJaEmitidaErro(AutomacaoErro):
    """Quando a nota já está emitida ou possui número preenchido."""
    pass