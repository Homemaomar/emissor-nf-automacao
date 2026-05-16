import ast
from tkinter import filedialog

import customtkinter as ctk

from database.db import carregar_config, salvar_config, usuario_e_gestor


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class TelaConfig(ctk.CTk):
    def __init__(self, usuario=None):
        super().__init__()

        self.usuario = usuario or {}
        self.is_admin = usuario_e_gestor(self.usuario)
        self.title("Configuração inicial")
        self.geometry("760x620")
        self.minsize(720, 580)

        self.config_atual = carregar_config()
        self.recorrencia_var = ctk.BooleanVar(
            value=self.config_atual.get("recurrence_enabled", False)
        )
        self.confirmacao_manual_var = ctk.BooleanVar(
            value=self.config_atual.get("confirmacao_manual_emissao", True)
        )

        self._criar_layout()
        self._preencher_campos()

    def _criar_layout(self):
        self.configure(fg_color="#0c111d")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkScrollableFrame(
            self,
            fg_color="#11182a",
            corner_radius=24,
            border_width=1,
            border_color="#24324a",
            scrollbar_button_color="#203a63",
            scrollbar_button_hover_color="#2c6bed",
        )
        container.grid(sticky="nsew", padx=28, pady=28)
        container.grid_columnconfigure(0, weight=1)

        hero = ctk.CTkFrame(container, fg_color="#16233d", corner_radius=20)
        hero.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 18))
        hero.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hero,
            text="Base operacional do emissor",
            font=("Segoe UI Semibold", 28, "bold"),
            text_color="#f5f7fb",
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(22, 8))

        ctk.CTkLabel(
            hero,
            text=(
                "Configure a base de arquivos, credenciais e a rotina padrao "
                "para deixar o produto pronto para operação recorrente."
            ),
            font=("Segoe UI", 14),
            text_color="#b7c2d9",
            justify="left",
            wraplength=620,
        ).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 22))

        form = ctk.CTkFrame(container, fg_color="#11182a")
        form.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 24))
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)

        self._criar_input_arquivo(form)
        self._criar_input_login(form)
        self._criar_input_senha(form)
        self._criar_input_notificacao(form)
        if self.is_admin:
            self._criar_input_email_envio(form)
            self._criar_input_senha_email_envio(form)
            self._criar_bloco_recorrencia(form, row=3, column=1)
            self._criar_bloco_confirmacao_emissao(form, row=4, column=0, colspan=2)
        else:
            self._criar_bloco_recorrencia(form, row=2, column=1)
            self._criar_bloco_confirmacao_emissao(form, row=3, column=0, colspan=2)
        self._criar_acoes(container)

    def _criar_input_arquivo(self, parent):
        bloco = self._bloco(parent, 0, 0, colspan=2)
        self._label(bloco, "Pasta base das notas")

        linha = ctk.CTkFrame(bloco, fg_color="transparent")
        linha.pack(fill="x", pady=(10, 0))
        linha.grid_columnconfigure(0, weight=1)

        self.entry_caminho = ctk.CTkEntry(
            linha,
            height=44,
            border_width=1,
            border_color="#304564",
            fg_color="#0e1626",
        )
        self.entry_caminho.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(
            linha,
            text="Selecionar",
            width=140,
            height=44,
            fg_color="#2c6bed",
            hover_color="#1f57c7",
            command=self.selecionar,
        ).pack(side="right")

    def _criar_input_login(self, parent):
        bloco = self._bloco(parent, 1, 0)
        self._label(bloco, "CNPJ / Login Nota Fiscal")
        self.entry_login = self._entry(bloco)
        self.entry_login.bind("<KeyRelease>", self._aplicar_mascara_cnpj)

    def _criar_input_senha(self, parent):
        bloco = self._bloco(parent, 1, 1)
        self._label(bloco, "Senha Nota Fiscal")
        self.entry_senha = self._entry(bloco, show="*")

    def _criar_input_notificacao(self, parent):
        bloco = self._bloco(parent, 2, 0)
        self._label(bloco, "Email para alertas")
        self.entry_email = self._entry(bloco)

    def _criar_input_email_envio(self, parent):
        bloco = self._bloco(parent, 2, 1)
        self._label(bloco, "Email para envio")
        self.entry_smtp_email = self._entry(bloco)

    def _criar_input_senha_email_envio(self, parent):
        bloco = self._bloco(parent, 3, 0)
        self._label(bloco, "Senha do email de envio")
        self.entry_smtp_password = self._entry(bloco, show="*")
        self.smtp_password_visivel = ctk.BooleanVar(value=False)
        self.switch_mostrar_smtp_password = ctk.CTkCheckBox(
            bloco,
            text="Mostrar senha",
            variable=self.smtp_password_visivel,
            onvalue=True,
            offvalue=False,
            text_color="#b7c2d9",
            fg_color="#2c6bed",
            hover_color="#1f57c7",
            command=self._alternar_visibilidade_senha_smtp,
        )
        self.switch_mostrar_smtp_password.pack(anchor="w", padx=18, pady=(0, 16))

    def _criar_bloco_recorrencia(self, parent, row, column):
        bloco = self._bloco(parent, row, column)
        self._label(bloco, "Recorrência padrão")

        self.switch_recorrencia = ctk.CTkSwitch(
            bloco,
            text="Ativar rotina automatica",
            variable=self.recorrencia_var,
            onvalue=True,
            offvalue=False,
            progress_color="#2c6bed",
        )
        self.switch_recorrencia.pack(anchor="w", pady=(12, 12))

        self.combo_recorrencia = ctk.CTkComboBox(
            bloco,
            height=42,
            values=[
                "manual",
                "diaria",
                "semanal",
                "fechamento_mensal",
            ],
            button_color="#203a63",
            border_color="#304564",
            fg_color="#0e1626",
        )
        self.combo_recorrencia.pack(fill="x")

    def _criar_bloco_confirmacao_emissao(self, parent, row, column, colspan=1):
        bloco = self._bloco(parent, row, column, colspan=colspan)
        self._label(bloco, "Confirmação antes de emitir")

        self.switch_confirmacao_manual = ctk.CTkSwitch(
            bloco,
            text="Pausar para o operador revisar e confirmar a emissão",
            variable=self.confirmacao_manual_var,
            onvalue=True,
            offvalue=False,
            progress_color="#2c6bed",
            text_color="#b7c2d9",
        )
        self.switch_confirmacao_manual.pack(anchor="w", padx=18, pady=(12, 6))

        ctk.CTkLabel(
            bloco,
            text=(
                "Ligado por padrão. Desligue apenas quando a base já estiver "
                "corrigida e a emissão puder seguir automaticamente."
            ),
            font=("Segoe UI", 12),
            text_color="#8ea3c7",
            justify="left",
            wraplength=920,
        ).pack(anchor="w", padx=18, pady=(0, 18))

    def _criar_acoes(self, parent):
        rodape = ctk.CTkFrame(parent, fg_color="transparent")
        rodape.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 24))
        rodape.grid_columnconfigure(0, weight=1)

        self.label_feedback = ctk.CTkLabel(
            rodape,
            text="",
            text_color="#ffcf70",
            font=("Segoe UI", 13),
        )
        self.label_feedback.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            rodape,
            text="Salvar configuração",
            width=190,
            height=46,
            font=("Segoe UI Semibold", 15, "bold"),
            fg_color="#2c6bed",
            hover_color="#1f57c7",
            command=self.salvar,
        ).grid(row=0, column=1, sticky="e")

    def _bloco(self, parent, row, column, colspan=1):
        bloco = ctk.CTkFrame(
            parent,
            fg_color="#141f34",
            corner_radius=18,
            border_width=1,
            border_color="#24324a",
        )
        bloco.grid(
            row=row,
            column=column,
            columnspan=colspan,
            sticky="nsew",
            padx=8,
            pady=8,
        )
        return bloco

    def _label(self, parent, text):
        ctk.CTkLabel(
            parent,
            text=text,
            font=("Segoe UI Semibold", 14, "bold"),
            text_color="#f5f7fb",
        ).pack(anchor="w", padx=18, pady=(18, 0))

    def _entry(self, parent, show=None):
        entry = ctk.CTkEntry(
            parent,
            height=44,
            show=show,
            border_width=1,
            border_color="#304564",
            fg_color="#0e1626",
        )
        entry.pack(fill="x", padx=18, pady=(10, 18))
        return entry

    def _alternar_visibilidade_senha_smtp(self):
        if not hasattr(self, "entry_smtp_password"):
            return
        self.entry_smtp_password.configure(
            show="" if self.smtp_password_visivel.get() else "*"
        )

    def _somente_digitos(self, valor):
        return "".join(ch for ch in str(valor or "") if ch.isdigit())

    def _formatar_cnpj(self, valor):
        digitos = self._somente_digitos(valor)[:14]
        partes = []

        if len(digitos) <= 2:
            return digitos

        partes.append(digitos[:2])
        if len(digitos) <= 5:
            return f"{partes[0]}.{digitos[2:]}"

        partes.append(digitos[2:5])
        if len(digitos) <= 8:
            return f"{partes[0]}.{partes[1]}.{digitos[5:]}"

        partes.append(digitos[5:8])
        if len(digitos) <= 12:
            return f"{partes[0]}.{partes[1]}.{partes[2]}/{digitos[8:]}"

        return f"{partes[0]}.{partes[1]}.{partes[2]}/{digitos[8:12]}-{digitos[12:]}"

    def _aplicar_mascara_cnpj(self, _event=None):
        if not hasattr(self, "entry_login"):
            return

        valor_formatado = self._formatar_cnpj(self.entry_login.get())
        self.entry_login.delete(0, "end")
        self.entry_login.insert(0, valor_formatado)
        self.entry_login.icursor("end")

    def _carregar_credenciais_email_legacy(self):
        try:
            with open("teste_envio.py", "r", encoding="utf-8") as arquivo:
                modulo = ast.parse(arquivo.read(), filename="teste_envio.py")
        except Exception:
            return "", ""

        for node in modulo.body:
            if not isinstance(node, ast.Assign):
                continue

            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "email_config":
                    try:
                        valor = ast.literal_eval(node.value)
                    except Exception:
                        return "", ""

                    if isinstance(valor, dict):
                        return (
                            str(valor.get("smtp_user", "") or "").strip(),
                            str(valor.get("smtp_password", "") or "").strip(),
                        )

        return "", ""

    def _preencher_campos(self):
        self.entry_caminho.insert(0, self.config_atual.get("caminho_base", ""))
        self.entry_login.insert(0, self._formatar_cnpj(self.config_atual.get("login", "")))
        self.entry_senha.insert(0, self.config_atual.get("senha", ""))
        self.entry_email.insert(0, self.config_atual.get("notification_email", ""))
        if self.is_admin:
            smtp_email = self.config_atual.get("smtp_sender_email", "")
            smtp_password = self.config_atual.get("smtp_sender_password", "")

            legacy_email, legacy_password = self._carregar_credenciais_email_legacy()
            if not smtp_email:
                smtp_email = legacy_email
            if not smtp_password:
                smtp_password = legacy_password

            self.entry_smtp_email.insert(0, smtp_email)
            self.entry_smtp_password.insert(0, smtp_password)
        self.combo_recorrencia.set(
            self.config_atual.get("recurrence_frequency", "manual")
        )

    def selecionar(self):
        pasta = filedialog.askdirectory()
        if pasta:
            self.entry_caminho.delete(0, "end")
            self.entry_caminho.insert(0, pasta)

    def salvar(self):
        caminho = self.entry_caminho.get().strip()
        login = self._somente_digitos(self.entry_login.get())
        senha = self.entry_senha.get().strip()
        email = self.entry_email.get().strip()
        smtp_sender_email = (
            self.entry_smtp_email.get().strip()
            if self.is_admin and hasattr(self, "entry_smtp_email")
            else self.config_atual.get("smtp_sender_email", "")
        )
        smtp_sender_password = (
            self.entry_smtp_password.get().strip()
            if self.is_admin and hasattr(self, "entry_smtp_password")
            else self.config_atual.get("smtp_sender_password", "")
        )
        recorrencia = self.combo_recorrencia.get().strip() or "manual"

        if not caminho or not login or not senha:
            self.label_feedback.configure(
                text="Preencha caminho, login e senha para continuar."
            )
            return

        salvar_config(
            caminho,
            login,
            senha,
            recurrence_enabled=self.recorrencia_var.get(),
            recurrence_frequency=recorrencia,
            notification_email=email,
            smtp_sender_email=smtp_sender_email,
            smtp_sender_password=smtp_sender_password,
            confirmacao_manual_emissao=self.confirmacao_manual_var.get(),
        )

        self.label_feedback.configure(text="Configuração salva com sucesso.")
        self.config_atual = carregar_config()
