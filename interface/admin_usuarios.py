import customtkinter as ctk

from database.db import aprovar_usuario, listar_usuarios_pendentes


class AdminUsuariosWindow(ctk.CTkToplevel):
    def __init__(self, parent, admin_user):
        super().__init__(parent)

        self.admin_user = admin_user
        self.title("Aprovacao de usuarios")
        self.geometry("760x560")
        self.configure(fg_color="#09111f")

        self._criar_layout()
        self.recarregar()

    def _criar_layout(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        topo = ctk.CTkFrame(
            self,
            fg_color="#0d1627",
            corner_radius=22,
            border_width=1,
            border_color="#24324a",
        )
        topo.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 18))

        ctk.CTkLabel(
            topo,
            text="Solicitacoes de acesso",
            font=("Segoe UI Semibold", 24, "bold"),
            text_color="#f5f7fb",
        ).pack(anchor="w", padx=20, pady=(18, 6))

        ctk.CTkLabel(
            topo,
            text="Apenas admins podem aprovar novos usuarios e liberar login.",
            font=("Segoe UI", 13),
            text_color="#9cadc8",
        ).pack(anchor="w", padx=20, pady=(0, 18))

        self.label_feedback = ctk.CTkLabel(
            self,
            text="",
            font=("Segoe UI", 12),
            text_color="#ffcf70",
        )
        self.label_feedback.grid(row=2, column=0, sticky="w", padx=24, pady=(0, 18))

        self.lista = ctk.CTkScrollableFrame(
            self,
            fg_color="#0d1627",
            corner_radius=22,
            border_width=1,
            border_color="#24324a",
        )
        self.lista.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 12))

    def recarregar(self):
        for child in self.lista.winfo_children():
            child.destroy()

        pendentes = listar_usuarios_pendentes()
        if not pendentes:
            ctk.CTkLabel(
                self.lista,
                text="Nao ha usuarios pendentes de aprovacao.",
                font=("Segoe UI", 14),
                text_color="#9cadc8",
            ).pack(anchor="w", padx=16, pady=16)
            return

        for usuario in pendentes:
            card = ctk.CTkFrame(
                self.lista,
                fg_color="#121b2d",
                corner_radius=18,
                border_width=1,
                border_color="#24324a",
            )
            card.pack(fill="x", padx=12, pady=8)

            ctk.CTkLabel(
                card,
                text=f"{usuario['nome']} ({usuario['username']})",
                font=("Segoe UI Semibold", 15, "bold"),
                text_color="#f5f7fb",
            ).pack(anchor="w", padx=16, pady=(16, 4))

            ctk.CTkLabel(
                card,
                text=f"Perfil solicitado: {usuario['role']} | Criado em: {usuario['created_at']}",
                font=("Segoe UI", 12),
                text_color="#9cadc8",
            ).pack(anchor="w", padx=16, pady=(0, 12))

            ctk.CTkButton(
                card,
                text="Aprovar acesso",
                width=150,
                fg_color="#2c6bed",
                hover_color="#1f57c7",
                command=lambda uid=usuario["id"], nome=usuario["nome"]: self._aprovar(uid, nome),
            ).pack(anchor="e", padx=16, pady=(0, 16))

    def _aprovar(self, user_id, nome):
        try:
            aprovar_usuario(user_id, self.admin_user)
        except Exception as exc:
            self.label_feedback.configure(text=str(exc))
            return

        self.label_feedback.configure(text=f"Acesso de {nome} aprovado com sucesso.")
        self.recarregar()
