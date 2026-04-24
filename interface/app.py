import os
import queue
import sys
import threading
import traceback
import unicodedata
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
import pandas as pd

from database.db import carregar_config, contar_notas_importadas, criar_banco, primeiro_acesso
from dados.leitor_planilha import PlanilhaNotasRepository, montar_caminho_planilha
from interface.admin_usuarios import AdminUsuariosWindow
from interface.importacao import ImportacaoWindow
from interface.login import LoginWindow
from interface.notas_banco import NotasBancoWindow
from interface.tela_config import TelaConfig
from utils.filtro_itens import interpretar_itens
from utils.orquestrador_emissao import OrquestradorEmissao


sys.path.append(str(Path(__file__).resolve().parent.parent))

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


THEME = {
    "app_bg": "#07111f",
    "app_bg_alt": "#0d1828",
    "sidebar_bg": "#08111e",
    "surface": "#101c2d",
    "surface_alt": "#162437",
    "surface_muted": "#1b2b41",
    "surface_soft": "#22344e",
    "border": "#223754",
    "border_strong": "#31507a",
    "text": "#f4f8ff",
    "text_muted": "#a5b4ca",
    "text_soft": "#6e839e",
    "primary": "#3894ff",
    "primary_hover": "#5da8ff",
    "primary_soft": "#0f2a49",
    "success": "#3ddc97",
    "info": "#6fb6ff",
    "warning": "#ffb757",
}


class StatusCard(ctk.CTkFrame):
    def __init__(self, parent, eyebrow, title, value, tone):
        super().__init__(
            parent,
            fg_color=THEME["surface"],
            corner_radius=22,
            border_width=1,
            border_color=THEME["border"],
        )

        tones = {
            "blue": (THEME["info"], THEME["text"]),
            "green": (THEME["success"], THEME["text"]),
            "amber": (THEME["primary"], THEME["text"]),
            "slate": (THEME["text_soft"], THEME["text"]),
        }
        accent, text = tones.get(tone, tones["slate"])

        ctk.CTkLabel(
            self,
            text=eyebrow.upper(),
            font=("Segoe UI Semibold", 9, "bold"),
            text_color=accent,
        ).pack(anchor="w", padx=16, pady=(14, 6))

        ctk.CTkLabel(
            self,
            text=title,
            font=("Segoe UI", 12),
            text_color=THEME["text_muted"],
        ).pack(anchor="w", padx=16)

        self.value_label = ctk.CTkLabel(
            self,
            text=value,
            font=("Segoe UI Semibold", 24, "bold"),
            text_color=text,
        )
        self.value_label.pack(anchor="w", padx=16, pady=(6, 14))


class EmissorApp(ctk.CTk):
    def __init__(self, usuario):
        super().__init__()

        self.usuario = usuario
        self.title("Emissor NFS-e")
        self.geometry("1440x860")
        self.minsize(1280, 780)
        self.configure(fg_color=THEME["app_bg"])

        self.config_data = carregar_config()
        self.base_notas = self.config_data.get("caminho_base", "")
        self.caminho_base = self.base_notas
        self.recurrence_enabled = self.config_data.get("recurrence_enabled", False)
        self.recurrence_frequency = self.config_data.get(
            "recurrence_frequency", "manual"
        )

        self.event_queue = queue.Queue()
        self.emissao_em_andamento = False
        self.prompt_interativo = None
        self.importacao_window = None
        self.notas_banco_window = None
        self.admin_window = None

        self._criar_layout()
        self.after(150, self.processar_fila_eventos)
        self.after(250, self.atualizar_dashboard)

    def _criar_layout(self):
        self.grid_propagate(False)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = self._criar_sidebar()
        self.sidebar.grid(row=0, column=0, sticky="nsw")

        self.main = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=THEME["surface_soft"],
            scrollbar_button_hover_color=THEME["primary"],
        )
        self.main.grid(row=0, column=1, sticky="nsew", padx=(0, 28), pady=28)
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_rowconfigure(3, weight=0)

        self._criar_topbar()
        self._criar_dashboard()
        self._criar_painel_execucao()
        self._criar_rodape_operacional()

    def _criar_sidebar(self):
        sidebar = ctk.CTkFrame(
            self,
            width=300,
            fg_color=THEME["sidebar_bg"],
            corner_radius=0,
            border_width=0,
        )
        sidebar.grid_rowconfigure(6, weight=1)

        brand = ctk.CTkFrame(
            sidebar,
            fg_color=THEME["surface_alt"],
            corner_radius=28,
            border_width=1,
            border_color=THEME["border"],
        )
        brand.grid(row=0, column=0, sticky="ew", padx=24, pady=(28, 20))

        ctk.CTkLabel(
            brand,
            text="Fiscal Flow",
            font=("Segoe UI Semibold", 30, "bold"),
            text_color=THEME["text"],
        ).pack(anchor="w", padx=22, pady=(22, 6))

        ctk.CTkLabel(
            brand,
            text="Operacao recorrente de emissao, envio e rastreio.",
            font=("Segoe UI", 13),
            text_color=THEME["text_muted"],
            justify="left",
            wraplength=220,
        ).pack(anchor="w", padx=22, pady=(0, 18))

        menu = [
            ("Painel operacional", None),
            ("Importar base", self.abrir_importacao),
            ("Historico de lotes", None),
            ("Recorrencia", None),
            ("Configuracoes", self.abrir_configuracao),
        ]

        if self.usuario.get("role") == "admin":
            menu.append(("Aprovar acessos", self.abrir_aprovacoes))

        for row, (text, command) in enumerate(menu, start=1):
            button = ctk.CTkButton(
                sidebar,
                text=text,
                anchor="w",
                height=46,
                fg_color=THEME["primary_soft"] if row == 1 else "transparent",
                hover_color=THEME["surface_alt"],
                text_color=THEME["text"] if row == 1 else THEME["text_muted"],
                corner_radius=18,
                command=command,
                border_width=1 if row == 1 else 0,
                border_color=THEME["border_strong"] if row == 1 else THEME["sidebar_bg"],
                font=("Segoe UI Semibold", 14, "bold") if row == 1 else ("Segoe UI", 14),
            )
            button.grid(row=row, column=0, sticky="ew", padx=24, pady=5)

        insight = ctk.CTkFrame(
            sidebar,
            fg_color=THEME["surface_alt"],
            corner_radius=22,
            border_width=1,
            border_color=THEME["border"],
        )
        insight.grid(row=7, column=0, sticky="sew", padx=24, pady=(20, 28))

        ctk.CTkLabel(
            insight,
            text="Sessao ativa",
            font=("Segoe UI Semibold", 14, "bold"),
            text_color=THEME["text"],
        ).pack(anchor="w", padx=16, pady=(16, 4))

        ctk.CTkLabel(
            insight,
            text=f"{self.usuario.get('nome')} ({self.usuario.get('role')})",
            font=("Segoe UI", 12),
            text_color=THEME["text_muted"],
            justify="left",
            wraplength=226,
        ).pack(anchor="w", padx=16, pady=(0, 6))

        self.label_recorrencia = ctk.CTkLabel(
            insight,
            text=self._texto_recorrencia(),
            font=("Segoe UI Semibold", 12, "bold"),
            text_color=THEME["primary"],
        )
        self.label_recorrencia.pack(anchor="w", padx=16, pady=(0, 14))

        return sidebar

    def _criar_topbar(self):
        topbar = ctk.CTkFrame(self.main, fg_color="transparent")
        topbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        topbar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            topbar,
            text="Painel de emissao",
            font=("Segoe UI Semibold", 22, "bold"),
            text_color=THEME["text"],
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(0, 0))

        meta = ctk.CTkFrame(topbar, fg_color="transparent")
        meta.grid(row=0, column=1, sticky="e", padx=6)

        self.label_usuario = ctk.CTkLabel(
            meta,
            text=f"Operador: {self.usuario.get('nome')}",
            font=("Segoe UI", 12),
            text_color=THEME["text_muted"],
        )
        self.label_usuario.pack(anchor="e", pady=(0, 2))

        self.label_base = ctk.CTkLabel(
            meta,
            text=f"Base: {self.base_notas or 'nao configurada'}",
            font=("Segoe UI", 11),
            text_color=THEME["text_soft"],
            wraplength=340,
            justify="right",
        )
        self.label_base.pack(anchor="e")

    def _criar_dashboard(self):
        self.workspace = ctk.CTkFrame(self.main, fg_color="transparent")
        self.workspace.grid(row=1, column=0, sticky="nsew", pady=(0, 16))
        self.workspace.grid_columnconfigure(0, weight=6)
        self.workspace.grid_columnconfigure(1, weight=5)
        self.workspace.grid_rowconfigure(1, weight=1)

        dash = ctk.CTkFrame(self.workspace, fg_color="transparent")
        dash.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 16))
        dash.grid_columnconfigure((0, 1, 2, 3), weight=1)

        specs = [
            ("Operacao", "Notas pendentes", "0", "blue"),
            ("Financeiro", "Valor em carteira", "R$ 0,00", "amber"),
            ("Resultado", "Emitidas no lote", "0", "green"),
            ("Importacao", "Notas no banco", str(contar_notas_importadas()), "amber"),
        ]

        self.dashboard_cards = []
        for index, (eyebrow, title, value, tone) in enumerate(specs):
            card = StatusCard(dash, eyebrow, title, value, tone)
            pad_left = 0 if index == 0 else 6
            pad_right = 0 if index == len(specs) - 1 else 6
            card.grid(row=0, column=index, sticky="nsew", padx=(pad_left, pad_right))
            self.dashboard_cards.append(card)

        self.lbl_pendentes = self.dashboard_cards[0].value_label
        self.lbl_valor = self.dashboard_cards[1].value_label
        self.lbl_emitidas = self.dashboard_cards[2].value_label
        self.lbl_importadas = self.dashboard_cards[3].value_label

        self._tornar_card_clicavel(
            self.dashboard_cards[3],
            self.abrir_notas_banco,
            "Abrir base",
        )

    def _criar_painel_execucao(self):
        self._criar_bloco_filtros(self.workspace)
        self._criar_bloco_resumo(self.workspace)

    def _criar_bloco_filtros(self, parent):
        bloco = ctk.CTkFrame(
            parent,
            fg_color=THEME["surface"],
            corner_radius=30,
            border_width=1,
            border_color=THEME["border"],
        )
        bloco.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        bloco.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(
            bloco,
            text="Fluxo de emissao",
            font=("Segoe UI Semibold", 18, "bold"),
            text_color=THEME["text"],
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(16, 10))

        self.combo_ano = self._combo(bloco, 1, 0, "Ano", ["2024", "2025", "2026", "2027"])
        self.combo_ano.set(str(datetime.now().year))

        self.combo_mes = self._combo(
            bloco,
            1,
            1,
            "Mes",
            [
                "01 - Janeiro",
                "02 - Fevereiro",
                "03 - Março",
                "04 - Abril",
                "05 - Maio",
                "06 - Junho",
                "07 - Julho",
                "08 - Agosto",
                "09 - Setembro",
                "10 - Outubro",
                "11 - Novembro",
                "12 - Dezembro",
            ],
        )
        self.combo_mes.set(f"{datetime.now():%m} - {self._nome_mes(datetime.now().month)}")

        self.combo_municipio = self._combo(
            bloco,
            1,
            2,
            "Municipio",
            ["Afogados da Ingazeira", "Triunfo", "Serra Talhada"],
        )
        self.combo_municipio.set("Afogados da Ingazeira")

        self.combo_cliente = self._combo(
            bloco, 2, 0, "Cliente", ["Todos", "Saude", "Educacao", "Assistencia"]
        )
        self.combo_cliente.set("Todos")

        self.combo_especie = self._combo(
            bloco, 2, 1, "Especie", ["Todas", "Reembolso", "Lote I", "Lote II", "Avulsa"]
        )
        self.combo_especie.set("Todas")

        modo_frame = ctk.CTkFrame(
            bloco,
            fg_color=THEME["surface_alt"],
            corner_radius=22,
            border_width=1,
            border_color=THEME["border"],
        )
        modo_frame.grid(row=2, column=2, sticky="nsew", padx=8, pady=(0, 10))

        ctk.CTkLabel(
            modo_frame,
            text="Modo de execucao",
            font=("Segoe UI Semibold", 12, "bold"),
            text_color=THEME["text"],
        ).pack(anchor="w", padx=14, pady=(10, 4))

        self.modo = ctk.StringVar(value="todas")
        for text, value in [
            ("Emitir tudo", "todas"),
            ("Emitir por item", "item"),
        ]:
            ctk.CTkRadioButton(
                modo_frame,
                text=text,
                variable=self.modo,
                value=value,
                text_color=THEME["text"],
                border_color=THEME["border_strong"],
                fg_color=THEME["primary"],
                hover_color=THEME["primary_hover"],
                font=("Segoe UI", 11),
                radiobutton_width=16,
                radiobutton_height=16,
                border_width_unchecked=2,
                border_width_checked=5,
            ).pack(anchor="w", padx=14, pady=1)

        self.entry_itens = ctk.CTkEntry(
            bloco,
            placeholder_text="Itens especificos. Ex: 1, 2, 5-8",
            height=34,
            border_width=1,
            border_color=THEME["border_strong"],
            fg_color=THEME["surface_alt"],
            text_color=THEME["text"],
            placeholder_text_color=THEME["text_soft"],
            corner_radius=14,
            font=("Segoe UI", 13),
        )
        self.entry_itens.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 10))

        acao_frame = ctk.CTkFrame(
            bloco,
            fg_color=THEME["surface_alt"],
            corner_radius=22,
            border_width=1,
            border_color=THEME["border"],
        )
        acao_frame.grid(row=3, column=2, sticky="e", padx=8, pady=(0, 10))

        self.botao_emitir = ctk.CTkButton(
            acao_frame,
            text="Iniciar emissao",
            width=156,
            height=36,
            font=("Segoe UI Semibold", 13, "bold"),
            fg_color=THEME["primary"],
            hover_color=THEME["primary_hover"],
            text_color="#06101d",
            command=self.iniciar_emissao,
        )
        self.botao_emitir.pack(side="left", padx=(10, 8), pady=8)

        ctk.CTkButton(
            acao_frame,
            text="Configurar",
            width=108,
            height=36,
            fg_color=THEME["surface_soft"],
            hover_color=THEME["surface_muted"],
            text_color=THEME["text"],
            border_width=1,
            border_color=THEME["border"],
            command=self.abrir_configuracao,
        ).pack(side="left", padx=(0, 10), pady=8)

        for combo in [self.combo_ano, self.combo_mes, self.combo_municipio]:
            combo.configure(command=self.on_filtro_change)

    def _criar_bloco_resumo(self, parent):
        bloco = ctk.CTkFrame(
            parent,
            fg_color=THEME["surface"],
            corner_radius=30,
            border_width=1,
            border_color=THEME["border"],
        )
        bloco.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(8, 0))
        bloco.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            bloco,
            text="Painel interativo",
            font=("Segoe UI Semibold", 18, "bold"),
            text_color=THEME["text"],
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 8))

        atalhos = ctk.CTkFrame(bloco, fg_color="transparent")
        atalhos.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        atalhos.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            atalhos,
            text="Importar base",
            height=38,
            corner_radius=16,
            fg_color=THEME["primary_soft"],
            hover_color=THEME["surface_soft"],
            text_color=THEME["text"],
            border_width=1,
            border_color=THEME["border_strong"],
            font=("Segoe UI Semibold", 12, "bold"),
            command=self.abrir_importacao,
        ).grid(row=0, column=0, sticky="ew", padx=0, pady=0)

        terminal_wrap = ctk.CTkFrame(
            bloco,
            fg_color=THEME["surface_alt"],
            corner_radius=22,
            border_width=1,
            border_color=THEME["border"],
        )
        terminal_wrap.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 10))
        terminal_wrap.grid_rowconfigure(1, weight=1)
        terminal_wrap.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            terminal_wrap,
            text="Console operacional",
            font=("Segoe UI Semibold", 13, "bold"),
            text_color=THEME["text"],
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        self.console_interativo = ctk.CTkTextbox(
            terminal_wrap,
            corner_radius=14,
            border_width=1,
            border_color=THEME["border"],
            fg_color="#091321",
            text_color=THEME["text"],
            font=("Consolas", 11),
            scrollbar_button_color=THEME["surface_soft"],
            scrollbar_button_hover_color=THEME["primary"],
        )
        self.console_interativo.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        entrada_wrap = ctk.CTkFrame(bloco, fg_color="transparent")
        entrada_wrap.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 18))
        entrada_wrap.grid_columnconfigure(0, weight=1)

        self.entry_comando = ctk.CTkEntry(
            entrada_wrap,
            placeholder_text="Digite um comando: status, importar, notas, aprovar, configurar, limpar",
            height=38,
            border_width=1,
            border_color=THEME["border_strong"],
            fg_color=THEME["surface_alt"],
            text_color=THEME["text"],
            placeholder_text_color=THEME["text_soft"],
            corner_radius=16,
        )
        self.entry_comando.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.entry_comando.bind("<Return>", self._on_comando_interativo)

        self.botao_comando = ctk.CTkButton(
            entrada_wrap,
            text="Executar",
            width=108,
            height=38,
            font=("Segoe UI Semibold", 13, "bold"),
            fg_color=THEME["primary"],
            hover_color=THEME["primary_hover"],
            text_color="#06101d",
            command=self.executar_comando_digitado,
        )
        self.botao_comando.grid(row=0, column=1, sticky="e")

        self.console_interativo.insert("end", "Sistema> Painel interativo pronto.\n")
        self.console_interativo.insert(
            "end",
            "Sistema> Comandos disponiveis: status, importar, notas, configurar, aprovar, limpar.\n",
        )
        self.console_interativo.configure(state="disabled")
        self._restaurar_modo_comando()

    def _criar_rodape_operacional(self):
        panel = ctk.CTkFrame(
            self.main,
            fg_color=THEME["surface"],
            corner_radius=26,
            border_width=1,
            border_color=THEME["border"],
        )
        panel.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        panel.grid_columnconfigure(0, weight=3)
        panel.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            panel,
            text="Monitor de execucao",
            font=("Segoe UI Semibold", 14, "bold"),
            text_color=THEME["text"],
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(8, 2))

        ctk.CTkLabel(
            panel,
            text="Logs legiveis, progresso e operador responsavel pelo lote.",
            font=("Segoe UI", 10),
            text_color=THEME["text_muted"],
        ).grid(row=0, column=1, sticky="w", padx=(0, 14), pady=(8, 2))

        left = ctk.CTkFrame(panel, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew", padx=(14, 8), pady=(0, 6))
        left.grid_columnconfigure(0, weight=1)

        self.progress = ctk.CTkProgressBar(
            left,
            height=6,
            progress_color=THEME["primary"],
            fg_color=THEME["surface_muted"],
            corner_radius=100,
        )
        self.progress.grid(row=0, column=0, sticky="ew")
        self.progress.set(0)

        self.label_progresso = ctk.CTkLabel(
            left,
            text="0 / 0 notas",
            font=("Segoe UI", 10),
            text_color=THEME["text_muted"],
        )
        self.label_progresso.grid(row=1, column=0, sticky="w", pady=(4, 0))

        right = ctk.CTkFrame(
            panel,
            fg_color=THEME["surface_alt"],
            corner_radius=16,
            border_width=1,
            border_color=THEME["border"],
        )
        right.grid(row=1, column=1, sticky="nsew", padx=(8, 14), pady=(0, 6))

        self.label_status_execucao = ctk.CTkLabel(
            right,
            text="Status atual: aguardando inicio.",
            font=("Segoe UI Semibold", 10, "bold"),
            text_color=THEME["primary"],
            justify="left",
            wraplength=250,
        )
        self.label_status_execucao.pack(anchor="w", padx=12, pady=(8, 4))

        self.label_proxima_etapa = ctk.CTkLabel(
            right,
            text="O proximo passo pode ser liberar usuarios pendentes ou iniciar um lote.",
            font=("Segoe UI", 9),
            text_color=THEME["text_muted"],
            justify="left",
            wraplength=250,
        )
        self.label_proxima_etapa.pack(anchor="w", padx=12, pady=(0, 4))

        self.label_responsavel = ctk.CTkLabel(
            right,
            text=f"Responsavel do lote: {self.usuario.get('nome')}",
            font=("Segoe UI", 9),
            text_color=THEME["text"],
            justify="left",
            wraplength=250,
        )
        self.label_responsavel.pack(anchor="w", padx=12, pady=(0, 8))

    def _combo(self, parent, row, column, label, values):
        wrap = ctk.CTkFrame(
            parent,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
        )
        wrap.grid(row=row, column=column, sticky="nsew", padx=8, pady=(0, 10))

        ctk.CTkLabel(
            wrap,
            text=label,
            font=("Segoe UI Semibold", 12, "bold"),
            text_color=THEME["text"],
        ).pack(anchor="w", padx=4, pady=(0, 4))

        combo = ctk.CTkComboBox(
            wrap,
            values=values,
            height=34,
            border_color=THEME["border_strong"],
            fg_color=THEME["surface_alt"],
            button_color=THEME["surface_soft"],
            button_hover_color=THEME["primary_soft"],
            dropdown_fg_color=THEME["surface_alt"],
            dropdown_hover_color=THEME["surface_muted"],
            text_color=THEME["text"],
            dropdown_text_color=THEME["text"],
            corner_radius=14,
            font=("Segoe UI", 13),
        )
        combo.pack(fill="x", padx=0, pady=(0, 0))
        return combo

    def _nome_mes(self, month_number):
        nomes = {
            1: "Janeiro",
            2: "Fevereiro",
            3: "Março",
            4: "Abril",
            5: "Maio",
            6: "Junho",
            7: "Julho",
            8: "Agosto",
            9: "Setembro",
            10: "Outubro",
            11: "Novembro",
            12: "Dezembro",
        }
        return nomes.get(month_number, "Janeiro")

    def _texto_recorrencia(self):
        if not self.recurrence_enabled:
            return "Recorrencia ainda manual"
        return f"Recorrencia ativa: {self.recurrence_frequency}"

    def abrir_configuracao(self):
        tela = TelaConfig(self.usuario)
        tela.mainloop()

        self.config_data = carregar_config()
        self.base_notas = self.config_data.get("caminho_base", "")
        self.caminho_base = self.base_notas
        self.recurrence_enabled = self.config_data.get("recurrence_enabled", False)
        self.recurrence_frequency = self.config_data.get("recurrence_frequency", "manual")
        self.label_base.configure(text=f"Base: {self.base_notas or 'nao configurada'}")
        self.label_recorrencia.configure(text=self._texto_recorrencia())
        self.atualizar_dashboard()

    def abrir_importacao(self):
        self.importacao_window = self._abrir_janela_unica(
            self.importacao_window,
            lambda: ImportacaoWindow(self, self.usuario),
        )

    def abrir_notas_banco(self):
        self.notas_banco_window = self._abrir_janela_unica(
            self.notas_banco_window,
            lambda: NotasBancoWindow(self),
        )

    def abrir_aprovacoes(self):
        if self.usuario.get("role") != "admin":
            self.logar("Apenas admins podem abrir a central de aprovacoes.")
            return
        self.admin_window = self._abrir_janela_unica(
            self.admin_window,
            lambda: AdminUsuariosWindow(self, self.usuario),
        )

    def on_filtro_change(self, _value=None):
        self.logar("Atualizando indicadores do lote selecionado...")
        self.atualizar_dashboard()

    def logar(self, texto):
        agora = datetime.now().strftime("%H:%M:%S")
        if hasattr(self, "log"):
            self.log.insert("end", f"[{agora}] {texto}\n")
            self.log.see("end")
        self._registrar_interacao(f"[{agora}] {texto}")

    def _registrar_interacao(self, texto):
        if not hasattr(self, "console_interativo"):
            return
        self.console_interativo.configure(state="normal")
        self.console_interativo.insert("end", f"{texto}\n")
        self.console_interativo.see("end")
        self.console_interativo.configure(state="disabled")

    def _normalizar_texto(self, texto):
        texto = unicodedata.normalize("NFKD", str(texto or ""))
        texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
        return " ".join(texto.strip().lower().split())

    def _restaurar_modo_comando(self):
        if not hasattr(self, "entry_comando") or not hasattr(self, "botao_comando"):
            return
        self.entry_comando.configure(
            placeholder_text="Digite um comando: status, importar, notas, aprovar, configurar, limpar"
        )
        self.botao_comando.configure(text="Executar")

    def _ativar_prompt_interativo(self, solicitacao):
        self.prompt_interativo = solicitacao
        payload = solicitacao.get("payload", {})
        opcoes = payload.get("opcoes", [])
        opcoes_texto = ", ".join(
            f"{opcao.get('id')}={opcao.get('label')}" for opcao in opcoes
        )

        self.entry_comando.configure(
            placeholder_text=f"Responda aqui: {opcoes_texto}"
        )
        self.botao_comando.configure(text="Responder")

        self._registrar_interacao("Sistema> Revisao final aguardando sua decisao.")
        for opcao in opcoes:
            self._registrar_interacao(
                f"Sistema> {opcao.get('id')} - {opcao.get('label')}"
            )

        self.label_status_execucao.configure(
            text="Status atual: aguardando sua decisao no painel interativo."
        )
        self.label_proxima_etapa.configure(
            text="Use o campo abaixo do console para responder 1, 2, 3 ou 4."
        )
        self.after(50, self.entry_comando.focus_force)

    def _resolver_prompt_interativo(self, comando):
        if not self.prompt_interativo:
            return False

        payload = self.prompt_interativo.get("payload", {})
        opcoes = payload.get("opcoes", [])
        comando_normalizado = self._normalizar_texto(comando)

        mapa_opcoes = {}
        for opcao in opcoes:
            identificador = str(opcao.get("id", "")).strip()
            label = opcao.get("label", "")
            if identificador:
                mapa_opcoes[identificador] = identificador
            if label:
                mapa_opcoes[self._normalizar_texto(label)] = identificador

        resposta = mapa_opcoes.get(comando_normalizado)
        if not resposta:
            self._registrar_interacao("Sistema> Resposta invalida. Use 1, 2, 3 ou 4.")
            return True

        opcao_escolhida = next(
            (opcao for opcao in opcoes if str(opcao.get("id")) == resposta),
            None,
        )
        if opcao_escolhida:
            self._registrar_interacao(
                f"Sistema> Opcao confirmada: {opcao_escolhida.get('label')}."
            )

        solicitacao = self.prompt_interativo
        self.prompt_interativo = None
        solicitacao["resposta"] = resposta
        solicitacao["evento"].set()

        self._restaurar_modo_comando()
        self.label_proxima_etapa.configure(
            text="O proximo passo pode ser liberar usuarios pendentes ou iniciar um lote."
        )
        return True

    def solicitar_input_interativo(self, payload):
        solicitacao = {
            "payload": payload or {},
            "resposta": None,
            "evento": threading.Event(),
        }
        self.event_queue.put(("input_request", solicitacao))
        solicitacao["evento"].wait()
        return solicitacao.get("resposta") or "4"

    def _on_comando_interativo(self, _event=None):
        self.executar_comando_digitado()

    def executar_comando_digitado(self):
        comando = self.entry_comando.get().strip()
        if not comando:
            return
        self.entry_comando.delete(0, "end")
        self._registrar_interacao(f"Operador> {comando}")
        if self._resolver_prompt_interativo(comando):
            return
        self.executar_comando_interativo(comando)

    def executar_comando_interativo(self, comando):
        comando_normalizado = (comando or "").strip().lower()

        if comando_normalizado in {"status", "painel", "resumo"}:
            self._mostrar_status_operacional()
        elif comando_normalizado in {"importar", "importacao", "base"}:
            self._registrar_interacao("Sistema> Abrindo a central de importacao.")
            self.abrir_importacao()
        elif comando_normalizado in {"notas", "ver notas", "banco"}:
            self._registrar_interacao("Sistema> Abrindo a base de notas importadas.")
            self.abrir_notas_banco()
        elif comando_normalizado in {"config", "configurar", "configuracoes"}:
            self._registrar_interacao("Sistema> Abrindo as configuracoes do produto.")
            self.abrir_configuracao()
        elif comando_normalizado in {"aprovar", "usuarios", "aprovar acessos"}:
            if self.usuario.get("role") != "admin":
                self._registrar_interacao("Sistema> Apenas admins podem aprovar acessos.")
                self.logar("Apenas admins podem abrir a central de aprovacoes.")
                return
            self._registrar_interacao("Sistema> Abrindo a central de aprovacao de usuarios.")
            self.abrir_aprovacoes()
        elif comando_normalizado in {"limpar", "clear", "cls"}:
            self.console_interativo.configure(state="normal")
            self.console_interativo.delete("1.0", "end")
            self.console_interativo.insert("end", "Sistema> Console limpo.\n")
            self.console_interativo.configure(state="disabled")
        else:
            self._registrar_interacao(
                "Sistema> Comando nao reconhecido. Use status, importar, notas, configurar, aprovar ou limpar."
            )

    def _mostrar_status_operacional(self):
        municipio = self.combo_municipio.get()
        periodo = f"{self.combo_mes.get()} / {self.combo_ano.get()}"
        pendentes = self.lbl_pendentes.cget("text")
        importadas = self.lbl_importadas.cget("text")
        self._registrar_interacao(
            f"Sistema> Periodo ativo: {periodo} | Municipio: {municipio} | Pendentes: {pendentes} | Notas no banco: {importadas}."
        )

    def processar_fila_eventos(self):
        try:
            while True:
                evento = self.event_queue.get_nowait()
                tipo = evento[0]
                if tipo == "log":
                    self.logar(evento[1])
                    self.label_status_execucao.configure(text=f"Status atual: {evento[1]}")
                elif tipo == "progress":
                    atual, total = evento[1], evento[2]
                    self.progress.set(atual / total if total > 0 else 0)
                    self.label_progresso.configure(text=f"{atual} / {total} notas")
                elif tipo == "input_request":
                    self._ativar_prompt_interativo(evento[1])
                elif tipo == "finish":
                    mensagem_final = evento[1] if len(evento) > 1 else "lote concluido."
                    self.botao_emitir.configure(state="normal")
                    self.emissao_em_andamento = False
                    if not self.prompt_interativo:
                        self._restaurar_modo_comando()
                    self.label_status_execucao.configure(text=f"Status atual: {mensagem_final}")
                    self.atualizar_dashboard()
                elif tipo == "erro":
                    self.label_status_execucao.configure(text=f"Status atual: erro - {evento[1]}")
                    self.logar(f"Erro: {evento[1]}")
        except queue.Empty:
            pass

        self.after(150, self.processar_fila_eventos)

    def iniciar_emissao(self):
        if self.emissao_em_andamento:
            self.logar("Ja existe uma emissao em andamento.")
            return

        try:
            caminho_planilha = montar_caminho_planilha(
                self.base_notas,
                self.combo_ano.get(),
                self.combo_mes.get(),
                self.combo_municipio.get(),
            )
        except Exception as exc:
            self.logar(f"Falha ao localizar planilha: {exc}")
            return

        itens = None
        if self.modo.get() == "item":
            texto = self.entry_itens.get().strip()
            if texto:
                itens = interpretar_itens(texto)

        self.emissao_em_andamento = True
        self.botao_emitir.configure(state="disabled")
        self.progress.set(0)
        self.label_progresso.configure(text="0 / 0 notas")
        self.logar(f"Planilha localizada: {caminho_planilha}")
        self.logar(f"Lote iniciado por {self.usuario.get('nome')}.")

        thread = threading.Thread(
            target=self.executar_emissao_thread,
            args=(
                caminho_planilha,
                self.combo_cliente.get(),
                self.combo_especie.get(),
                itens,
            ),
            daemon=True,
        )
        thread.start()

    def executar_emissao_thread(self, caminho_planilha, cliente, especie, itens):
        mensagem_final = "lote concluido."
        try:
            leitor = PlanilhaNotasRepository(caminho_planilha)
            atualizador = leitor

            orquestrador = OrquestradorEmissao(
                leitor_planilha=leitor,
                atualizador_planilha=atualizador,
                usuario=self.usuario,
                log_callback=lambda msg: self.event_queue.put(("log", msg)),
                progresso_callback=lambda atual, total: self.event_queue.put(("progress", atual, total)),
                finish_callback=None,
                input_callback=self.solicitar_input_interativo,
            )

            filtros = {
                "ano": self.combo_ano.get(),
                "mes": self.combo_mes.get(),
                "municipio": self.combo_municipio.get(),
                "cliente": cliente,
                "especie": especie,
                "modo_emissao": self.modo.get(),
                "itens": itens if itens else None,
            }

            resultado = orquestrador.executar(
                caminho_planilha=caminho_planilha,
                filtros=filtros,
                headless=False,
            ) or {}
            mensagem_final = resultado.get("mensagem_final", "lote concluido.")
        except Exception as exc:
            traceback.print_exc()
            mensagem_final = f"erro - {exc}"
            self.event_queue.put(("erro", str(exc)))
        finally:
            self.event_queue.put(("finish", mensagem_final))

    def atualizar_dashboard(self):
        try:
            caminho = montar_caminho_planilha(
                self.base_notas,
                self.combo_ano.get(),
                self.combo_mes.get(),
                self.combo_municipio.get(),
            )
            if not caminho or not os.path.exists(caminho):
                self.lbl_pendentes.configure(text="0")
                self.lbl_valor.configure(text="R$ 0,00")
                self.lbl_emitidas.configure(text="0")
                self.lbl_importadas.configure(text=str(contar_notas_importadas()))
                return

            xls = pd.ExcelFile(caminho, engine="openpyxl")
            nome_aba = next((aba for aba in xls.sheet_names if aba.strip().upper() == "NOTAS"), None)
            if not nome_aba:
                self.logar("Aba NOTAS nao encontrada na planilha.")
                return

            df = pd.read_excel(xls, sheet_name=nome_aba)
            xls.close()

            pendentes = len(df[df["STATUS"] == "PENDENTE"]) if "STATUS" in df.columns else 0
            emitidas = len(df[df["STATUS"] == "EMITIDA"]) if "STATUS" in df.columns else 0
            valor_total = df["VALOR"].sum() if "VALOR" in df.columns else 0

            self.lbl_pendentes.configure(text=str(pendentes))
            self.lbl_valor.configure(text=f"R$ {valor_total:,.2f}")
            self.lbl_emitidas.configure(text=str(emitidas))
            self.lbl_importadas.configure(text=str(contar_notas_importadas()))
        except Exception as exc:
            self.logar(f"Erro ao atualizar dashboard: {exc}")

    def _tornar_card_clicavel(self, card, command, button_text):
        botao = ctk.CTkButton(
            card,
            text=button_text,
            width=84,
            height=26,
            fg_color="transparent",
            hover_color=THEME["surface_muted"],
            text_color=THEME["primary"],
            border_width=0,
            font=("Segoe UI Semibold", 12, "bold"),
            command=command,
        )
        botao.place(relx=1.0, y=16, x=-18, anchor="ne")

        card.bind("<Button-1>", lambda _event: command())
        for child in card.winfo_children():
            if child is not botao:
                child.bind("<Button-1>", lambda _event: command())

    def _abrir_janela_unica(self, referencia, factory):
        if referencia is not None and referencia.winfo_exists():
            referencia.deiconify()
            referencia.lift()
            referencia.focus_force()
            referencia.attributes("-topmost", True)
            referencia.after(250, lambda: referencia.attributes("-topmost", False))
            return referencia

        janela = factory()
        janela.transient(self)
        janela.lift()
        janela.focus_force()
        janela.attributes("-topmost", True)
        janela.after(250, lambda: janela.attributes("-topmost", False))
        return janela


def iniciar_sistema():
    criar_banco()
    login = LoginWindow()
    login.mainloop()

    if not login.usuario_autenticado:
        return

    if primeiro_acesso():
        tela = TelaConfig(login.usuario_autenticado)
        tela.mainloop()

    app = EmissorApp(login.usuario_autenticado)
    app.mainloop()


if __name__ == "__main__":
    iniciar_sistema()

