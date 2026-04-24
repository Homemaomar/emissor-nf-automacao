import os
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

from database.db import (
    criar_modelo_recorrente_de_nota,
    salvar_nota_importada,
)


HEADER_ALIASES = {
    "cliente_nome": ["cliente", "nome", "razao social", "tomador", "nome cliente", "cliente/razao social", "secretaria"],
    "cliente_documento": ["cnpj", "cpf", "documento", "cnpj cpf"],
    "cliente_email": ["email", "e-mail", "mail"],
    "descricao": ["descricao", "discriminacao", "servico", "descricao servico"],
    "valor_servico": ["valor", "valor servico", "valor total", "valor nota"],
    "ir": ["ir", "irrf"],
    "iss": ["iss", "issqn"],
    "municipio": ["municipio", "cidade"],
    "ctn": ["ctn"],
    "nbs": ["nbs"],
    "competencia_ano": ["ano", "competencia ano"],
    "competencia_mes": ["mes", "competencia mes"],
    "status": ["status"],
    "item": ["item"],
    "especie": ["especie", "espécie"],
}


def _normalizar_texto(texto):
    texto = str(texto or "").strip().lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return " ".join(texto.split())


def _local_name(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _to_float(valor):
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    if valor is None:
        return 0.0
    texto = str(valor).strip()
    if not texto:
        return 0.0

    # Trata formatos comuns:
    # 15.777,68 -> 15777.68
    # 15777,68 -> 15777.68
    # 15777.68 -> 15777.68
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return 0.0


def _match_column(columns, aliases):
    normalized = {_normalizar_texto(col): col for col in columns}
    for alias in aliases:
        key = _normalizar_texto(alias)
        if key in normalized:
            return normalized[key]
    return None


def _valor_coluna(row, columns, aliases):
    col = _match_column(columns, aliases)
    return row.get(col, "") if col else ""


def _mapear_linha_excel(row, source_file, source_ref, ano_padrao="", mes_padrao=""):
    origem = Path(source_file)
    municipio_path = origem.parent.name if origem.parent else ""
    mes_path = ""
    ano_path = ""
    try:
        mes_path = origem.parent.parent.name
        ano_path = origem.parent.parent.parent.name
    except Exception:
        pass

    data = {
        "source_type": "excel",
        "source_file": source_file,
        "source_ref": source_ref,
        "cliente_nome": "",
        "cliente_documento": "",
        "cliente_email": "",
        "descricao": "",
        "valor_servico": 0.0,
        "ir": 0.0,
        "iss": 0.0,
        "municipio": municipio_path,
        "ctn": "",
        "nbs": "",
        "competencia_ano": ano_padrao or ano_path,
        "competencia_mes": mes_padrao or mes_path[:2],
        "status": "IMPORTADA",
        "item": "",
        "especie": "",
    }

    columns = list(row.index)

    # Prioriza colunas operacionais da planilha para evitar colisao com aliases genericos.
    data["cliente_nome"] = _valor_coluna(
        columns=columns,
        row=row,
        aliases=["cliente.1", "cliente", "secretaria"],
    )
    data["descricao"] = _valor_coluna(
        columns=columns,
        row=row,
        aliases=["descricao", "descrição", "discriminacao", "servico", "descricao servico", "cliente"],
    )

    for target, aliases in HEADER_ALIASES.items():
        if target in {"cliente_nome", "descricao"} and str(data.get(target) or "").strip():
            continue
        col = _match_column(columns, aliases)
        if col:
            data[target] = row.get(col, "")

    data["valor_servico"] = _to_float(data.get("valor_servico"))
    data["ir"] = _to_float(data.get("ir"))
    data["iss"] = _to_float(data.get("iss"))
    data["cliente_nome"] = str(data.get("cliente_nome") or "").strip()
    data["cliente_documento"] = str(data.get("cliente_documento") or "").strip()
    data["cliente_email"] = str(data.get("cliente_email") or "").strip().lower()
    data["descricao"] = str(data.get("descricao") or "").strip()
    data["municipio"] = str(data.get("municipio") or "").strip()
    data["ctn"] = str(data.get("ctn") or "").strip()
    data["nbs"] = str(data.get("nbs") or "").strip()
    data["competencia_ano"] = str(data.get("competencia_ano") or ano_padrao or "").strip()
    data["competencia_mes"] = str(data.get("competencia_mes") or mes_padrao or "").strip()
    data["status_origem"] = str(data.get("status") or "").strip().upper()
    data["status"] = "IMPORTADA"
    data["item"] = str(data.get("item") or "").strip()
    data["especie"] = str(data.get("especie") or "").strip()

    key_base = "|".join(
        [
            _normalizar_texto(data["cliente_documento"] or data["cliente_nome"]),
            _normalizar_texto(data["descricao"]),
            _normalizar_texto(data["municipio"]),
            str(round(data["valor_servico"], 2)),
        ]
    )
    data["recorrente_key"] = key_base
    data["recorrente_score"] = 95 if data["cliente_documento"] and data["descricao"] else 50
    return data


def importar_excel_para_banco(paths, usuario, ano_padrao="", mes_padrao=""):
    resultados = []
    for path in paths:
        arquivo = Path(path)
        xls = pd.ExcelFile(arquivo, engine="openpyxl")
        try:
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                if df.empty:
                    continue

                for index, row in df.fillna("").iterrows():
                    if not any(str(v).strip() for v in row.tolist()):
                        continue

                    nota = _mapear_linha_excel(
                        row,
                        source_file=str(arquivo),
                        source_ref=f"{sheet}:{index + 2}",
                        ano_padrao=ano_padrao,
                        mes_padrao=mes_padrao,
                    )
                    if nota.get("status_origem") and nota["status_origem"] != "PENDENTE":
                        continue

                    nota_id = salvar_nota_importada(nota, usuario)
                    resultados.append(
                        {
                            "nota_id": nota_id,
                            "source_file": str(arquivo),
                            "cliente_nome": nota["cliente_nome"],
                            "descricao": nota["descricao"],
                            "valor_servico": nota["valor_servico"],
                            "recorrente_score": nota["recorrente_score"],
                        }
                    )
        finally:
            xls.close()
    return resultados


def _buscar_primeiro_texto(root, nomes):
    nomes_normalizados = {_normalizar_texto(nome) for nome in nomes}
    for element in root.iter():
        if _normalizar_texto(_local_name(element.tag)) in nomes_normalizados:
            valor = str(element.text or "").strip()
            if valor:
                return valor
    return ""


def _parse_xml(path, ano_padrao="", mes_padrao=""):
    root = ET.parse(path).getroot()
    cliente_nome = _buscar_primeiro_texto(
        root,
        ["RazaoSocial", "xNome", "Nome", "TomadorRazaoSocial"],
    )
    cliente_documento = _buscar_primeiro_texto(
        root,
        ["Cnpj", "CPF", "Documento", "TomadorCpfCnpj"],
    )
    cliente_email = _buscar_primeiro_texto(root, ["Email", "EmailTomador"])
    descricao = _buscar_primeiro_texto(
        root,
        ["Discriminacao", "Descricao", "xProd", "Servico"],
    )
    valor_servico = _to_float(
        _buscar_primeiro_texto(root, ["ValorServicos", "vNF", "Valor", "ValorServico"])
    )
    municipio = _buscar_primeiro_texto(root, ["Municipio", "xMun", "Cidade"])
    ctn = _buscar_primeiro_texto(root, ["CTN", "CodigoTributacaoNacional"])
    nbs = _buscar_primeiro_texto(root, ["NBS"])
    ir = _to_float(_buscar_primeiro_texto(root, ["ValorIr", "IRRF", "Ir"]))
    iss = _to_float(_buscar_primeiro_texto(root, ["ValorIss", "ISSQN", "Iss"]))
    numero = _buscar_primeiro_texto(root, ["Numero", "nNF", "NumeroNfse"])

    nota = {
        "source_type": "xml",
        "source_file": str(path),
        "source_ref": numero or Path(path).stem,
        "cliente_nome": cliente_nome,
        "cliente_documento": cliente_documento,
        "cliente_email": cliente_email.lower(),
        "descricao": descricao,
        "valor_servico": valor_servico,
        "ir": ir,
        "iss": iss,
        "municipio": municipio,
        "ctn": ctn,
        "nbs": nbs,
        "competencia_ano": str(ano_padrao or ""),
        "competencia_mes": str(mes_padrao or ""),
        "status": "IMPORTADA",
    }
    nota["recorrente_key"] = "|".join(
        [
            _normalizar_texto(cliente_documento or cliente_nome),
            _normalizar_texto(descricao),
            _normalizar_texto(municipio),
            str(round(valor_servico, 2)),
        ]
    )
    nota["recorrente_score"] = 95 if cliente_documento and descricao else 60
    return nota


def importar_xml_para_banco(paths, usuario, ano_padrao="", mes_padrao=""):
    resultados = []
    for path in paths:
        nota = _parse_xml(path, ano_padrao=ano_padrao, mes_padrao=mes_padrao)
        nota_id = salvar_nota_importada(nota, usuario)
        resultados.append(
            {
                "nota_id": nota_id,
                "source_file": str(path),
                "cliente_nome": nota["cliente_nome"],
                "descricao": nota["descricao"],
                "valor_servico": nota["valor_servico"],
                "recorrente_score": nota["recorrente_score"],
            }
        )
    return resultados


def criar_modelos_recorrentes_automaticos(notas_importadas, usuario):
    modelos_ids = []
    for nota in notas_importadas:
        if int(nota.get("recorrente_score", 0)) >= 90 and nota.get("nota_id"):
            modelo_id = criar_modelo_recorrente_de_nota(nota["nota_id"], usuario)
            modelos_ids.append(modelo_id)
    return modelos_ids
