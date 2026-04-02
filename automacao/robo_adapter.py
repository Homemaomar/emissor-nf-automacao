import time


class RoboEmissorNFSe:

    def __init__(self, config=None):

        self.config = config or {}

    def emitir(self, nota):

        # SIMULAÇÃO

        time.sleep(2)

        item = nota["item"]

        numero_nf = f"NF{item}"

        return {

            "numero_nfse": numero_nf,
            "caminho_xml": f"C:/Notas/XML/{numero_nf}.xml",
            "caminho_pdf": f"C:/Notas/PDF/{numero_nf}.pdf"
        }