from pathlib import Path
from datetime import datetime
import pandas as pd
from openpyxl import load_workbook



class PlanilhaNotasRepository:

    def __init__(self, caminho_planilha):

        self.caminho_planilha = Path(caminho_planilha)

        if not self.caminho_planilha.exists():
            raise FileNotFoundError(
                f"Planilha não encontrada: {self.caminho_planilha}"
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
            raise Exception("Aba 'NOTAS' não encontrada")

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
        # NORMALIZAÇÃO ROBUSTA
        # ===============================
        def normalizar(col):
            return (
                str(col)
                .strip()
                .upper()
                .replace("Ç", "C")
                .replace("Ã", "A")
                .replace("Á", "A")
                .replace("É", "E")
                .replace("Í", "I")
                .replace("Ó", "O")
                .replace("Ú", "U")
            )

        df.columns = [normalizar(col) for col in df.columns]

        print("COLUNAS NORMALIZADAS:", df.columns.tolist())

        # ===============================
        # VALIDAÇÃO OBRIGATÓRIA
        # ===============================
        colunas_necessarias = ["STATUS", "ITEM"]

        for col in colunas_necessarias:
            if col not in df.columns:
                raise Exception(
                    f"Coluna obrigatória '{col}' não encontrada.\n"
                    f"Colunas disponíveis: {df.columns.tolist()}"
                )

        # ===============================
        # GARANTIR TIPOS
        # ===============================
        df["STATUS"] = df["STATUS"].astype(str)
        df["ITEM"] = df["ITEM"].astype(str)

        return df

    def obter_dados_item(self, item_id):
        """
        Recarrega a planilha e retorna os dados atualizados de um item específico
        """

        df = self._carregar_planilha()

        linha = df[df["ITEM"] == str(item_id)]

        if linha.empty:
            raise Exception(f"Item {item_id} não encontrado na planilha.")

        dados = linha.iloc[0].to_dict()

        self._log(f"Dados recarregados do item {item_id}")

        return dados

    # ==========================================
    # LISTAR NOTAS PENDENTES (PADRÃO OFICIAL)
    # ==========================================
    def listar_notas_pendentes(self, secretaria=None, especie=None, itens=None):

        df = self.df.copy()

        # 🔍 DEBUG AQUI (AGORA SIM)
        print("📊 COLUNAS DO DF:", df.columns.tolist())
        print("📊 DESCRICAO DF:")
        print(df["DESCRICAO"].head())

        # STATUS
        df = df[df["STATUS"].str.upper() == "PENDENTE"]

        # SECRETARIA
        if secretaria and secretaria != "Todas":
            df = df[df["SECRETARIA"] == secretaria]

        # ESPÉCIE
        if especie and especie != "Todas":
            df = df[df["ESPÉCIE"] == especie]

        # ITENS
        if itens:
            df = df[df["ITEM"].isin(itens)]

        df = df.reset_index()

        notas = []

        for _, row in df.iterrows():

            notas.append({

                "excel_row": int(row["index"]) + 2,

                "item": row.get("ITEM", ""),
                "descricao": row.get("DESCRICAO", ""),  # 🔥 CORRETO
                "valor": row.get("VALOR", 0),
                "ir": row.get("IR", 0),
                "iss": row.get("ISS", 0),
                "cnpj": row.get("CNPJ", ""),
                "ctn": row.get("CTN", ""),
                "nbs": row.get("NBS", ""),
                "email": row.get("EMAIL", "")
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

        # 🔥 Usa aba ativa (seguro)
        ws = wb.active

        headers = {}

        # Mapear cabeçalhos
        for col in range(1, ws.max_column + 1):
            nome = ws.cell(row=1, column=col).value
            if nome:
                headers[nome] = col

        def set_val(coluna, valor):
            if coluna in headers:
                ws.cell(row=excel_row, column=headers[coluna], value=valor)

        # Atualizações padrão
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
        f"❌ Nenhuma planilha encontrada em:\n{pasta}\n\n"
        f"Arquivos encontrados:\n" +
        "\n".join(str(a.name) for a in arquivos_encontrados)
    )