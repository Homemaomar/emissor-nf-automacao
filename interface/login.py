import webbrowser

import customtkinter as ctk

from database.db import (
    autenticar_usuario,
    contar_usuarios,
    criar_usuario,
    obter_gestor_local,
    usuario_dono_sistema,
    usuario_e_gestor,
    validar_status_cobranca_online,
)


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

PORTAL_PAGAMENTO_URL = "https://mbsduodigital.com/"
RECURSOS_COMPLETOS = ["emissao_nfse", "envio_email", "envio_whatsapp"]


class LoginWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Acesso do operador")
        self.geometry("880x660")
        self.minsize(820, 620)
        self.configure(fg_color="#09111f")

        self.usuario_autenticado = None

        self._criar_layout()
        if contar_usuarios() == 0:
            self.tabview.set("Solicitar acesso")
            self._mostrar_feedback(
                "Nenhum usuário encontrado. O primeiro cadastro será o gestor local "
                "e precisa usar o email pago no portal."
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
                "O gestor local usa o email que está pago no portal. Depois disso, "
                "ele pode aprovar até 3 usuários comuns neste computador."
            ),
            font=("Segoe UI", 15),
            text_color="#b8c4da",
            justify="left",
            wraplength=420,
        ).pack(anchor="w", padx=28, pady=(0, 12))

        ctk.CTkLabel(
            hero,
            text=(
                "Teste grátis por 3 dias. Depois da contagem, o acesso só continua "
                "com mensalidade ativa no portal."
            ),
            font=("Segoe UI Semibold", 15, "bold"),
            text_color="#ffcf70",
            justify="left",
            wraplength=420,
        ).pack(anchor="w", padx=28, pady=(0, 22))

        for title, body in [
            ("Gestor vinculado", "O primeiro usuário vira gestor e passa pela validação online do portal."),
            ("Delegação limitada", "Usuários comuns aguardam aprovação e não podem virar gestores."),
            ("Pagamento obrigatório", "Sem assinatura ativa no site, o acesso ao desktop é bloqueado."),
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
            wraplength=300,
            justify="left",
        )
        self.label_feedback.grid(row=3, column=0, sticky="w", padx=22, pady=(0, 10))

        self.link_pagamento = ctk.CTkButton(
            painel,
            text="Abrir portal de pagamento",
            height=34,
            fg_color="transparent",
            hover_color="#16233d",
            text_color="#6ea8ff",
            border_width=1,
            border_color="#2c6bed",
            corner_radius=14,
            command=self._abrir_portal_pagamento,
        )
        self.link_pagamento.grid(row=4, column=0, sticky="w", padx=22, pady=(0, 18))
        self.link_pagamento.grid_remove()

    def _abrir_portal_pagamento(self):
        webbrowser.open(PORTAL_PAGAMENTO_URL)

    def _mostrar_feedback(self, texto, mostrar_link=False):
        self.label_feedback.configure(text=texto)
        if mostrar_link:
            self.link_pagamento.grid()
        else:
            self.link_pagamento.grid_remove()

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
        self.register_password_confirm = self._entry(parent, "Confirmar senha", show="*")

        self.register_show_password = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            parent,
            text="Mostrar senha",
            variable=self.register_show_password,
            onvalue=True,
            offvalue=False,
            text_color="#9cadc8",
            fg_color="#2c6bed",
            hover_color="#1f57c7",
            border_color="#6c7c96",
            command=self._alternar_senha_cadastro,
        ).pack(anchor="w", pady=(10, 0))

        self.role_combo = ctk.CTkComboBox(
            parent,
            values=["operador"],
            height=44,
            border_color="#304564",
            fg_color="#121b2d",
            button_color="#203a63",
            state="readonly",
        )
        self.role_combo.pack(fill="x", pady=(10, 0))
        self.role_combo.set("operador")

        ctk.CTkButton(
            parent,
            text="Solicitar usuário comum",
            height=46,
            font=("Segoe UI Semibold", 14, "bold"),
            fg_color="#2c6bed",
            hover_color="#1f57c7",
            command=self._registrar,
        ).pack(fill="x", pady=(18, 8))

    def _alternar_senha_cadastro(self):
        show = "" if self.register_show_password.get() else "*"
        self.register_password.configure(show=show)
        self.register_password_confirm.configure(show=show)

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

    def _anexar_licenca_usuario(self, usuario, licenca, email_licenca):
        assinatura = (licenca or {}).get("assinatura") or {}
        recursos = assinatura.get("recursos") or []
        if not recursos and (licenca or {}).get("reason") == "owner_bypass":
            recursos = RECURSOS_COMPLETOS

        usuario["email_licenca"] = email_licenca
        usuario["licenca"] = licenca or {}
        usuario["plano_code"] = assinatura.get("plano_code") or ""
        usuario["plano_nome"] = assinatura.get("plano_nome") or assinatura.get("nome") or ""
        usuario["recursos"] = list(recursos)
        return usuario

    def _login(self):
        username = self.login_username.get().strip()
        password = self.login_password.get()

        resultado = autenticar_usuario(username, password)
        if not resultado.get("ok"):
            reason = resultado.get("reason")
            mensagens = {
                "invalid_credentials": "Usuário ou senha inválidos.",
                "pending_approval": "Seu acesso ainda aguarda aprovação do gestor.",
                "inactive_user": "Seu usuário está inativo. Fale com o gestor.",
                "billing_overdue": "Mensalidade vencida. Clique no link abaixo para atualizar o pagamento e liberar o acesso.",
                "billing_blocked": "Assinatura bloqueada. Clique no link abaixo para regularizar o pagamento.",
            }
            self._mostrar_feedback(
                mensagens.get(reason, "Não foi possível entrar com esse email."),
                mostrar_link=reason in {"billing_overdue", "billing_blocked"},
            )
            return

        usuario = resultado["usuario"]
        gestor = obter_gestor_local()
        email_licenca = username if usuario_e_gestor(usuario) else (gestor or {}).get("username", "")

        if usuario_dono_sistema(email_licenca):
            licenca = {
                "ok": True,
                "reason": "owner_bypass",
                "assinatura": {
                    "plano_code": "owner",
                    "plano_nome": "Gestor MBS",
                    "recursos": RECURSOS_COMPLETOS,
                },
            }
        else:
            licenca = validar_status_cobranca_online(email_licenca)
            if not licenca.get("ok"):
                mensagens = {
                    "billing_overdue": "Mensalidade vencida. Clique no link abaixo para atualizar o pagamento e liberar o acesso.",
                    "billing_blocked": "Assinatura bloqueada. Clique no link abaixo para regularizar o pagamento.",
                    "billing_grace_period": "Assinatura em carência. Clique no link abaixo para conferir a mensalidade.",
                    "billing_not_configured": "Assinatura não encontrada. Clique no link abaixo para contratar ou atualizar o pagamento.",
                    "billing_online_disabled": "Validação online da assinatura está desativada.",
                    "billing_validation_failed": "Não foi possível validar a assinatura online. Verifique a internet e tente novamente.",
                    "billing_online_inactive": "Assinatura sem pagamento ativo. Clique no link abaixo para atualizar o pagamento.",
                    "billing_unknown": "Assinatura sem status pago. Clique no link abaixo para regularizar.",
                    "license_email_not_found": "Este email não está cadastrado no portal. Clique no link abaixo para contratar ou regularizar.",
                    "license_client_inactive": "Este cliente está inativo no portal. Clique no link abaixo para regularizar.",
                    "license_subscription_not_found": "Este email não possui assinatura ativa no portal.",
                    "license_subscription_inactive": "A assinatura deste email não está ativa no portal.",
                    "license_subscription_overdue": "A assinatura deste email está vencida. Clique no link abaixo para atualizar o pagamento.",
                    "license_machine_required": "Não foi possível identificar este computador para validar a licença.",
                    "license_device_not_authorized": "Esta licença já está vinculada a outro computador. Regularize o acesso no portal.",
                }
                reason = licenca.get("reason")
                self._mostrar_feedback(
                    mensagens.get(reason, "Clique no link abaixo para atualizar o pagamento."),
                    mostrar_link=reason != "billing_validation_failed",
                )
                return

        usuario = self._anexar_licenca_usuario(usuario, licenca, email_licenca)
        self.usuario_autenticado = usuario
        self.destroy()

    def _registrar(self):
        senha = self.register_password.get()
        confirmar_senha = self.register_password_confirm.get()
        if senha != confirmar_senha:
            self._mostrar_feedback("As senhas digitadas não conferem.")
            return

        try:
            resultado = criar_usuario(
                nome=self.register_name.get().strip(),
                username=self.register_username.get().strip(),
                password=senha,
                role=self.role_combo.get().strip().lower(),
            )
        except Exception as exc:
            self._mostrar_feedback(str(exc))
            return

        if resultado["primeiro_usuario"]:
            self._mostrar_feedback("Gestor local criado. Faça login para validar a assinatura no portal.")
        else:
            self._mostrar_feedback("Solicitação criada. Aguarde a aprovação do gestor local.")

        self.tabview.set("Entrar")
        self.login_username.delete(0, "end")
        self.login_username.insert(0, self.register_username.get().strip())
        self.login_password.delete(0, "end")
