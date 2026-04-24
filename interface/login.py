import customtkinter as ctk

from database.db import autenticar_usuario, contar_usuarios, criar_usuario


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class LoginWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Acesso do operador")
        self.geometry("880x620")
        self.minsize(820, 560)
        self.configure(fg_color="#09111f")

        self.usuario_autenticado = None

        self._criar_layout()
        if contar_usuarios() == 0:
            self.tabview.set("Solicitar acesso")
            self.label_feedback.configure(
                text=(
                    "Nenhum usuario encontrado. O primeiro cadastro sera promovido "
                    "a admin e liberado imediatamente."
                )
            )

    def _criar_layout(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkFrame(
            self,
            fg_color="#0f1728",
            corner_radius=28,
            border_width=1,
            border_color="#24324a",
        )
        container.grid(sticky="nsew", padx=28, pady=28)
        container.grid_columnconfigure(0, weight=3)
        container.grid_columnconfigure(1, weight=2)

        self._criar_hero(container)
        self._criar_formulario(container)

    def _criar_hero(self, parent):
        hero = ctk.CTkFrame(
            parent,
            fg_color="#15233d",
            corner_radius=24,
            border_width=1,
            border_color="#24324a",
        )
        hero.grid(row=0, column=0, sticky="nsew", padx=(24, 12), pady=24)

        ctk.CTkLabel(
            hero,
            text="Controle de acesso",
            font=("Segoe UI Semibold", 34, "bold"),
            text_color="#f5f7fb",
        ).pack(anchor="w", padx=28, pady=(34, 10))

        ctk.CTkLabel(
            hero,
            text=(
                "Novos usuarios nao entram direto no sistema. Depois do primeiro "
                "admin, cada cadastro fica pendente ate aprovacao."
            ),
            font=("Segoe UI", 15),
            text_color="#b8c4da",
            justify="left",
            wraplength=420,
        ).pack(anchor="w", padx=28, pady=(0, 28))

        for title, body in [
            ("Acesso controlado", "O primeiro usuario vira admin. Os demais aguardam aprovacao."),
            ("Rastreabilidade", "Cada emissao continua vinculada ao operador autenticado."),
            ("Governanca", "Aprovacao acontece dentro do painel por um usuario admin."),
        ]:
            card = ctk.CTkFrame(
                hero,
                fg_color="#121b2d",
                corner_radius=18,
                border_width=1,
                border_color="#24324a",
            )
            card.pack(fill="x", padx=28, pady=8)

            ctk.CTkLabel(
                card,
                text=title,
                font=("Segoe UI Semibold", 15, "bold"),
                text_color="#f5f7fb",
            ).pack(anchor="w", padx=18, pady=(16, 4))

            ctk.CTkLabel(
                card,
                text=body,
                font=("Segoe UI", 13),
                text_color="#9cadc8",
                justify="left",
                wraplength=360,
            ).pack(anchor="w", padx=18, pady=(0, 16))

    def _criar_formulario(self, parent):
        painel = ctk.CTkFrame(
            parent,
            fg_color="#0d1627",
            corner_radius=24,
            border_width=1,
            border_color="#24324a",
        )
        painel.grid(row=0, column=1, sticky="nsew", padx=(12, 24), pady=24)
        painel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            painel,
            text="Acesso do sistema",
            font=("Segoe UI Semibold", 24, "bold"),
            text_color="#f5f7fb",
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(24, 8))

        ctk.CTkLabel(
            painel,
            text="Entre com um email aprovado ou solicite um novo acesso.",
            font=("Segoe UI", 13),
            text_color="#9cadc8",
            wraplength=280,
            justify="left",
        ).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 16))

        self.tabview = ctk.CTkTabview(
            painel,
            fg_color="#0d1627",
            segmented_button_selected_color="#2c6bed",
            segmented_button_selected_hover_color="#1f57c7",
            segmented_button_unselected_color="#16233d",
            segmented_button_unselected_hover_color="#223250",
        )
        self.tabview.grid(row=2, column=0, sticky="nsew", padx=22, pady=(0, 16))
        self.tabview.add("Entrar")
        self.tabview.add("Solicitar acesso")

        self._criar_tab_login(self.tabview.tab("Entrar"))
        self._criar_tab_cadastro(self.tabview.tab("Solicitar acesso"))

        self.label_feedback = ctk.CTkLabel(
            painel,
            text="",
            font=("Segoe UI", 12),
            text_color="#ffcf70",
            wraplength=280,
            justify="left",
        )
        self.label_feedback.grid(row=3, column=0, sticky="w", padx=22, pady=(0, 18))

    def _criar_tab_login(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        self.login_username = self._entry(parent, "Email de acesso")
        self.login_password = self._entry(parent, "Senha", show="*")

        ctk.CTkButton(
            parent,
            text="Entrar no painel",
            height=46,
            font=("Segoe UI Semibold", 14, "bold"),
            fg_color="#2c6bed",
            hover_color="#1f57c7",
            command=self._login,
        ).pack(fill="x", pady=(18, 8))

    def _criar_tab_cadastro(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        self.register_name = self._entry(parent, "Nome completo")
        self.register_username = self._entry(parent, "Email de acesso")
        self.register_password = self._entry(parent, "Senha", show="*")

        self.role_combo = ctk.CTkComboBox(
            parent,
            values=["operador", "gestor"],
            height=44,
            border_color="#304564",
            fg_color="#121b2d",
            button_color="#203a63",
        )
        self.role_combo.pack(fill="x", pady=(10, 0))
        self.role_combo.set("operador")

        ctk.CTkButton(
            parent,
            text="Solicitar usuario",
            height=46,
            font=("Segoe UI Semibold", 14, "bold"),
            fg_color="#2c6bed",
            hover_color="#1f57c7",
            command=self._registrar,
        ).pack(fill="x", pady=(18, 8))

    def _entry(self, parent, placeholder, show=None):
        entry = ctk.CTkEntry(
            parent,
            placeholder_text=placeholder,
            height=44,
            show=show,
            border_width=1,
            border_color="#304564",
            fg_color="#121b2d",
        )
        entry.pack(fill="x", pady=(10, 0))
        return entry

    def _login(self):
        username = self.login_username.get().strip()
        password = self.login_password.get()

        resultado = autenticar_usuario(username, password)
        if not resultado.get("ok"):
            reason = resultado.get("reason")
            mensagens = {
                "invalid_credentials": "Usuario ou senha invalidos.",
                "pending_approval": "Seu acesso ainda aguarda aprovacao do admin.",
                "inactive_user": "Seu usuario esta inativo. Fale com o admin.",
                "billing_overdue": "Mensalidade vencida. Regularize a assinatura para liberar o acesso.",
                "billing_blocked": "Assinatura bloqueada. Fale com o administrador financeiro.",
            }
            self.label_feedback.configure(
                text=mensagens.get(reason, "Nao foi possivel entrar com esse email.")
            )
            return

        self.usuario_autenticado = resultado["usuario"]
        self.destroy()

    def _registrar(self):
        try:
            resultado = criar_usuario(
                nome=self.register_name.get().strip(),
                username=self.register_username.get().strip(),
                password=self.register_password.get(),
                role=self.role_combo.get().strip().lower(),
            )
        except Exception as exc:
            self.label_feedback.configure(text=str(exc))
            return

        if resultado["primeiro_usuario"]:
            self.label_feedback.configure(
                text="Primeiro usuario criado como admin. Faça login para continuar."
            )
        else:
            self.label_feedback.configure(
                text="Solicitacao criada. Aguarde a aprovacao de um admin."
            )

        self.tabview.set("Entrar")
        self.login_username.delete(0, "end")
        self.login_username.insert(0, self.register_username.get().strip())
        self.login_password.delete(0, "end")
