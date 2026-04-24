from pathlib import Path
from datetime import datetime
import pandas as pd
from openpyxl import load_workbook
import os


class PlanilhaNotasRepository:

    def __init__(self, caminho_planilha):

        self.caminho_planilha = Path(caminho_planilha)

        if not self.caminho_planilha.exists():
            raise FileNotFoundError(
                f"Planilha nÃ£o encontrada: {self.caminho_planilha}"
            )

        self.df = self._carregar_planilha()

    # ==========================================
    # CARREGAR PLANILHA
    # ==========================================
    def _carregar_planilha(self):

        xls = pd.ExcelFile(self.caminho_planilha, engine="openpyxl")

        abas_normalizadas = [a.upper().strip() for a in xls.sheet_names]

        if "NOTAS" in abas_normalizadas:
            nome_aba_real = xls.sheet_names[
                abas_normalizadas.index("NOTAS")
            ]
        else:
            raise Exception("Aba 'NOTAS' nÃ£o encontrada")

        df = pd.read_excel(
            self.caminho_planilha,
            sheet_name=nome_aba_real,
            engine="openpyxl"
        )

        # ===============================
        # DEBUG (ver colunas reais)
        # ===============================
        print("COLUNAS ORIGINAIS:", df.columns.tolist())

        # ===============================
        # NORMALIZAÃ‡ÃƒO ROBUSTA
        # ===============================
        def normalizar(col):
            return (
                str(col)
                .strip()
                .upper()
                .replace("Ã‡", "C")
                .replace("Ãƒ", "A")
                .replace("Ã", "A")
                .replace("Ã‰", "E")
                .replace("Ã", "I")
                .replace("Ã“", "O")
                .replace("Ãš", "U")
            )

        df.columns = [normalizar(col) for col in df.columns]

        print("COLUNAS NORMALIZADAS:", df.columns.tolist())

        # ===============================
        # VALIDAÃ‡ÃƒO OBRIGATÃ“RIA
        # ===============================
        colunas_necessarias = ["STATUS", "ITEM"]

        for col in colunas_necessarias:
            if col not in df.columns:
                raise Exception(
                    f"Coluna obrigatÃ³ria '{col}' nÃ£o encontrada.\n"
                    f"Colunas disponÃ­veis: {df.columns.tolist()}"
                )

        # ===============================
        # GARANTIR TIPOS
        # ===============================
        df["STATUS"] = df["STATUS"].astype(str)
        df["ITEM"] = df["ITEM"].astype(str)

        return df

    def _coluna_cliente(self, df):
        if "CLIENTE.1" in df.columns:
            return "CLIENTE.1"
        if "CLIENTE" in df.columns and "DESCRICAO" in df.columns:
            return "CLIENTE"
        if "SECRETARIA" in df.columns:
            return "SECRETARIA"
        if "CLIENTE" in df.columns:
            return "CLIENTE"
        return None

    def _coluna_descricao(self, df):
        if "DESCRICAO" in df.columns:
            return "DESCRICAO"
        if "DESCRIÇÃO" in df.columns:
            return "DESCRIÇÃO"
        if "CLIENTE.1" in df.columns and "CLIENTE" in df.columns:
            return "CLIENTE"
        return None

    def obter_dados_item(self, item_id):
        """
        Recarrega a planilha e retorna os dados atualizados de um item especÃ­fico
        """

        df = self._carregar_planilha()

        linha = df[df["ITEM"] == str(item_id)]

        if linha.empty:
            raise Exception(f"Item {item_id} nÃ£o encontrado na planilha.")

        dados = linha.iloc[0].to_dict()

        self._log(f"Dados recarregados do item {item_id}")

        return dados

    # ==========================================
    # LISTAR NOTAS PENDENTES (PADRÃƒO OFICIAL)
    # ==========================================
    def listar_notas_pendentes(self, cliente=None, especie=None, itens=None):

        df = self.df.copy()
        coluna_cliente = self._coluna_cliente(df)
        coluna_descricao = self._coluna_descricao(df)

        # ðŸ” DEBUG AQUI (AGORA SIM)
        print("ðŸ“Š COLUNAS DO DF:", df.columns.tolist())
        print("ðŸ“Š COLUNA CLIENTE:", coluna_cliente)
        print("ðŸ“Š COLUNA DESCRICAO:", coluna_descricao)

        # STATUS
        df = df[df["STATUS"].str.upper() == "PENDENTE"]

        # CLIENTE
        if cliente and cliente != "Todos":
            if coluna_cliente:
                df = df[df[coluna_cliente] == cliente]
            else:
                df = df.iloc[0:0]

        # ESPÃ‰CIE
        if especie and especie != "Todas":
            df = df[df["ESPÃ‰CIE"] == especie]

        # ITENS
        if itens:
            df = df[df["ITEM"].isin(itens)]

        df = df.reset_index()

        notas = []

        for _, row in df.iterrows():

            notas.append({

                "excel_row": int(row["index"]) + 2,

                "item": row.get("ITEM", ""),
                "cliente": row.get(coluna_cliente, "") if coluna_cliente else "",
                "descricao": row.get(coluna_descricao, "") if coluna_descricao else "",
                "valor": row.get("VALOR", 0),
                "ir": row.get("IR", 0),
                "iss": row.get("ISS", 0),
                "cnpj": row.get("CNPJ", ""),
                "ctn": row.get("CTN", ""),
                "nbs": row.get("NBS", ""),
                "email": row.get("EMAIL", ""),
                "especie": row.get("ESPECIE", row.get("ESPÉCIE", "")),
            })

        return notas

    # ==========================================
    # ATUALIZAR RESULTADO NA PLANILHA
    # ==========================================
    def atualizar_resultado_emissao(
        self,
        excel_row,
        status,
        usuario,
        numero_nfse="",
        caminho_xml="",
        caminho_pdf="",
        erro=""
    ):

        wb = load_workbook(self.caminho_planilha, keep_vba=True)

        # ðŸ”¥ Usa aba ativa (seguro)
        ws = wb.active

        headers = {}

        # Mapear cabeÃ§alhos
        for col in range(1, ws.max_column + 1):
            nome = ws.cell(row=1, column=col).value
            if nome:
                headers[nome] = col

        def set_val(coluna, valor):
            if coluna in headers:
                ws.cell(row=excel_row, column=headers[coluna], value=valor)

        # AtualizaÃ§Ãµes padrÃ£o
        set_val("STATUS", status)
        set_val("EMITIDA_POR", usuario)

        if status == "EMITIDA":
            set_val("NUMERO_NFSE", numero_nfse)
            set_val("DATA_EMISSAO", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
            set_val("CAMINHO_XML", caminho_xml)
            set_val("CAMINHO_PDF", caminho_pdf)

        if status == "ERRO":
            set_val("ERRO", erro)

        wb.save(self.caminho_planilha)


# ==========================================
# MONTAR CAMINHO DA PLANILHA
# ==========================================


def montar_caminho_planilha(base_notas, ano, mes, municipio):

    base = Path(base_notas)
    mes = str(mes or "").strip()
    municipio = str(municipio or "").strip()

    # ==========================
    # VALIDAÇÃO DA BASE
    # ==========================
    if not base.exists():
        raise FileNotFoundError(
            f"❌ Caminho base não encontrado:\n{base}"
        )

    # ==========================
    # MONTAR PASTA
    # ==========================
    pasta = base / ano / mes / municipio
    aliases_mes = {
        "03 - Marco": "03 - Março",
        "03 - Março": "03 - Marco",
    }

    if not pasta.exists() and mes in aliases_mes:
        pasta_alternativa = base / ano / aliases_mes[mes] / municipio
        if pasta_alternativa.exists():
            pasta = pasta_alternativa

    if not pasta.exists():
        raise FileNotFoundError(
            f"❌ Pasta não encontrada:\n{pasta}"
        )

    # ==========================
    # ARQUIVOS POSSÍVEIS
    # ==========================
    arquivo_xlsx = pasta / "notas.xlsx"
    arquivo_xlsm = pasta / "notas.xlsm"

    # ==========================
    # PRIORIDADE (.xlsm primeiro)
    # ==========================
    if arquivo_xlsm.exists():
        return str(arquivo_xlsm)

    if arquivo_xlsx.exists():
        return str(arquivo_xlsx)

    # ==========================
    # ERRO DETALHADO
    # ==========================
    arquivos_encontrados = list(pasta.glob("*"))

    raise FileNotFoundError(
        f"âŒ Nenhuma planilha encontrada em:\n{pasta}\n\n"
        f"Arquivos encontrados:\n" +
        "\n".join(str(a.name) for a in arquivos_encontrados)
    )
