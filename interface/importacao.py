from tkinter import filedialog

import customtkinter as ctk

from dados.importadores import (
    criar_modelos_recorrentes_automaticos,
    importar_excel_para_banco,
    importar_xml_para_banco,
)
from database.db import (
    contar_notas_importadas,
    excluir_notas_importadas_sem_cliente,
    excluir_todas_notas_importadas,
    listar_modelos_recorrentes,
    listar_notas_importadas,
)


class ImportacaoWindow(ctk.CTkToplevel):
    def __init__(self, parent, usuario):
        super().__init__(parent)

        self.usuario = usuario
        self.title("Central de importacao")
        self.geometry("1100x720")
        self.configure(fg_color="#09111f")
        self.transient(parent)
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(250, lambda: self.attributes("-topmost", False))
        self.filtro_sem_cliente = ctk.BooleanVar(value=False)
        self.filtro_ultimas = ctk.BooleanVar(value=True)

        self._criar_layout()
        self.recarregar()

    def _criar_layout(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        hero = ctk.CTkFrame(
            self,
            fg_color="#0d1627",
            corner_radius=22,
            border_width=1,
            border_color="#24324a",
        )
        hero.grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(24, 18))

        ctk.CTkLabel(
            hero,
            text="Central de importacao e recorrencia",
            font=("Segoe UI Semibold", 28, "bold"),
            text_color="#f5f7fb",
        ).pack(anchor="w", padx=20, pady=(20, 6))

        ctk.CTkLabel(
            hero,
            text=(
                "Importe multiplos XMLs ou planilhas para o banco e aproveite "
                "modelos recorrentes para clientes que repetem notas todo mes."
            ),
            font=("Segoe UI", 13),
            text_color="#9cadc8",
            justify="left",
            wraplength=920,
        ).pack(anchor="w", padx=20, pady=(0, 18))

        filtros = ctk.CTkFrame(hero, fg_color="transparent")
        filtros.pack(fill="x", padx=20, pady=(0, 18))

        ctk.CTkSwitch(
            filtros,
            text="Ocultar registros sem cliente",
            variable=self.filtro_sem_cliente,
            command=self.recarregar,
            progress_color="#2c6bed",
        ).pack(side="left", padx=(0, 14))

        ctk.CTkSwitch(
            filtros,
            text="Destacar importacao mais recente",
            variable=self.filtro_ultimas,
            command=self.recarregar,
            progress_color="#2c6bed",
        ).pack(side="left")

        self.label_feedback = ctk.CTkLabel(
            self,
            text="",
            font=("Segoe UI", 12),
            text_color="#ffcf70",
            justify="left",
            wraplength=1000,
        )
        self.label_feedback.grid(row=2, column=0, columnspan=2, sticky="w", padx=24, pady=(12, 24))

        self.lista_notas = ctk.CTkScrollableFrame(
            self,
            fg_color="#0d1627",
            corner_radius=22,
            border_width=1,
            border_color="#24324a",
        )
        self.lista_notas.grid(row=1, column=0, sticky="nsew", padx=(24, 12), pady=(0, 0))

        lateral = ctk.CTkFrame(
            self,
            fg_color="#0d1627",
            corner_radius=22,
            border_width=1,
            border_color="#24324a",
        )
        lateral.grid(row=1, column=1, sticky="nsew", padx=(12, 24), pady=(0, 0))

        ctk.CTkLabel(
            lateral,
            text="Acoes",
            font=("Segoe UI Semibold", 18, "bold"),
            text_color="#f5f7fb",
        ).pack(anchor="w", padx=18, pady=(18, 12))

        ctk.CTkButton(
            lateral,
            text="Importar XMLs",
            height=44,
            fg_color="#2c6bed",
            hover_color="#1f57c7",
            command=self._importar_xml,
        ).pack(fill="x", padx=18, pady=6)

        ctk.CTkButton(
            lateral,
            text="Importar planilhas",
            height=44,
            fg_color="#2c6bed",
            hover_color="#1f57c7",
            command=self._importar_excel,
        ).pack(fill="x", padx=18, pady=6)

        ctk.CTkButton(
            lateral,
            text="Excluir sem cliente",
            height=40,
            fg_color="#7a4d16",
            hover_color="#8d5a19",
            command=self._limpar_sem_cliente,
        ).pack(fill="x", padx=18, pady=(14, 6))

        ctk.CTkButton(
            lateral,
            text="Limpar todas as importacoes",
            height=40,
            fg_color="#7b2430",
            hover_color="#8b2b38",
            command=self._limpar_todas,
        ).pack(fill="x", padx=18, pady=6)

        self.label_total = ctk.CTkLabel(
            lateral,
            text="0 notas importadas",
            font=("Segoe UI Semibold", 14, "bold"),
            text_color="#d7deed",
        )
        self.label_total.pack(anchor="w", padx=18, pady=(16, 10))

        ctk.CTkLabel(
            lateral,
            text="Modelos recorrentes",
            font=("Segoe UI Semibold", 18, "bold"),
            text_color="#f5f7fb",
        ).pack(anchor="w", padx=18, pady=(12, 10))

        self.lista_modelos = ctk.CTkScrollableFrame(
            lateral,
            fg_color="#121b2d",
            corner_radius=18,
            border_width=1,
            border_color="#24324a",
            width=320,
        )
        self.lista_modelos.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    def _importar_xml(self):
        arquivos = filedialog.askopenfilenames(
            title="Selecionar XMLs",
            filetypes=[("Arquivos XML", "*.xml")],
        )
        if not arquivos:
            return

        notas = importar_xml_para_banco(arquivos, self.usuario)
        modelos = criar_modelos_recorrentes_automaticos(notas, self.usuario)
        self.label_feedback.configure(
            text=f"{len(notas)} nota(s) de XML importada(s). {len(modelos)} modelo(s) recorrente(s) criado(s)."
        )
        self.recarregar()

    def _importar_excel(self):
        arquivos = filedialog.askopenfilenames(
            title="Selecionar planilhas",
            filetypes=[("Planilhas Excel", "*.xlsx *.xlsm")],
        )
        if not arquivos:
            return

        notas = importar_excel_para_banco(arquivos, self.usuario)
        modelos = criar_modelos_recorrentes_automaticos(notas, self.usuario)
        self.label_feedback.configure(
            text=f"{len(notas)} nota(s) de Excel importada(s). {len(modelos)} modelo(s) recorrente(s) criado(s)."
        )
        self.recarregar()

    def _limpar_sem_cliente(self):
        removidas = excluir_notas_importadas_sem_cliente()
        self.label_feedback.configure(
            text=f"{removidas} importacao(oes) sem cliente foram removidas."
        )
        self.recarregar()

    def _limpar_todas(self):
        resultado = excluir_todas_notas_importadas()
        self.label_feedback.configure(
            text=f"Limpeza concluida: {resultado['notas']} nota(s) e {resultado['modelos']} modelo(s) removidos."
        )
        self.recarregar()

    def recarregar(self):
        for child in self.lista_notas.winfo_children():
            child.destroy()
        for child in self.lista_modelos.winfo_children():
            child.destroy()

        notas = listar_notas_importadas(limit=40)
        modelos = listar_modelos_recorrentes(limit=20)

        if self.filtro_sem_cliente.get():
            notas = [n for n in notas if (n.get("cliente_nome") or "").strip()]

        self.label_total.configure(text=f"{contar_notas_importadas()} notas importadas")

        if not notas:
            ctk.CTkLabel(
                self.lista_notas,
                text="Nenhuma nota importada para o filtro atual.",
                font=("Segoe UI", 14),
                text_color="#9cadc8",
            ).pack(anchor="w", padx=16, pady=16)
        else:
            destaque_id = notas[0]["id"] if self.filtro_ultimas.get() else None

            for nota in notas:
                destaque = nota["id"] == destaque_id
                card = ctk.CTkFrame(
                    self.lista_notas,
                    fg_color="#16233d" if destaque else "#121b2d",
                    corner_radius=18,
                    border_width=1,
                    border_color="#4c76c9" if destaque else "#24324a",
                )
                card.pack(fill="x", padx=12, pady=8)

                titulo = nota.get("cliente_nome") or "Sem cliente identificado"
                origem = nota.get("source_type", "").upper()
                descricao = nota.get("descricao") or "Sem descricao"
                valor = float(nota.get("valor_servico", 0) or 0)
                score = int(nota.get("recorrente_score", 0) or 0)
                tag = "ULTIMA IMPORTACAO | " if destaque else ""

                ctk.CTkLabel(
                    card,
                    text=f"{tag}{titulo} | {origem}",
                    font=("Segoe UI Semibold", 15, "bold"),
                    text_color="#f5f7fb",
                ).pack(anchor="w", padx=16, pady=(16, 4))

                ctk.CTkLabel(
                    card,
                    text=(
                        f"{descricao}\n"
                        f"Valor: R$ {valor:,.2f} | "
                        f"Recorrencia: {score}% | "
                        f"Importado por: {nota.get('imported_by_name', '-')}"
                    ),
                    font=("Segoe UI", 12),
                    text_color="#9cadc8",
                    justify="left",
                    wraplength=620,
                ).pack(anchor="w", padx=16, pady=(0, 16))

        if not modelos:
            ctk.CTkLabel(
                self.lista_modelos,
                text="Nenhum modelo recorrente gerado ainda.",
                font=("Segoe UI", 13),
                text_color="#9cadc8",
                wraplength=260,
                justify="left",
            ).pack(anchor="w", padx=12, pady=12)
        else:
            for modelo in modelos:
                card = ctk.CTkFrame(
                    self.lista_modelos,
                    fg_color="#0e1626",
                    corner_radius=16,
                    border_width=1,
                    border_color="#24324a",
                )
                card.pack(fill="x", padx=8, pady=6)

                ctk.CTkLabel(
                    card,
                    text=modelo.get("nome_modelo", "Modelo"),
                    font=("Segoe UI Semibold", 14, "bold"),
                    text_color="#f5f7fb",
                ).pack(anchor="w", padx=12, pady=(12, 4))

                ctk.CTkLabel(
                    card,
                    text=(
                        f"{modelo.get('cliente_nome', '')}\n"
                        f"Periodicidade: {modelo.get('periodicidade', 'mensal')}"
                    ),
                    font=("Segoe UI", 12),
                    text_color="#9cadc8",
                    justify="left",
                    wraplength=260,
                ).pack(anchor="w", padx=12, pady=(0, 12))
