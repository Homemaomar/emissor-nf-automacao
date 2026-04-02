from pathlib import Path

def montar_caminho_planilha(base_notas, ano, mes, municipio):

    base = Path(base_notas)

    if not base.exists():
        raise FileNotFoundError(f"Base não encontrada: {base}")

    pasta = base / ano / mes / municipio

    if not pasta.exists():
        raise FileNotFoundError(f"Pasta não encontrada: {pasta}")

    arquivo_xlsx = pasta / "notas.xlsx"
    arquivo_xlsm = pasta / "notas.xlsm"

    if arquivo_xlsm.exists():
        return str(arquivo_xlsm)

    if arquivo_xlsx.exists():
        return str(arquivo_xlsx)

    raise FileNotFoundError(f"Nenhuma planilha encontrada em: {pasta}")


# 🔥 TESTE REAL
base_notas = r"C:\Users\Antônio Marcos\Desktop\Notas"
ano = "2026"
mes = "02 - Fevereiro"
municipio = "Afogados da Ingazeira"

caminho = montar_caminho_planilha(base_notas, ano, mes, municipio)

