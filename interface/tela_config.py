import customtkinter as ctk
from tkinter import filedialog
from database.db import salvar_config

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class TelaConfig(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Configuração Inicial")
        self.geometry("600x420")

        self.criar_layout()

    def criar_layout(self):

        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=30, pady=30)

        titulo = ctk.CTkLabel(
            frame,
            text="⚙ Configuração Inicial",
            font=("Arial", 22, "bold")
        )
        titulo.pack(anchor="w", pady=(10, 20))

        # CAMINHO BASE
        ctk.CTkLabel(frame, text="Caminho Base").pack(anchor="w")

        linha = ctk.CTkFrame(frame, fg_color="transparent")
        linha.pack(fill="x", pady=5)

        self.entry_caminho = ctk.CTkEntry(linha)
        self.entry_caminho.pack(side="left", fill="x", expand=True, padx=(0,10))

        ctk.CTkButton(
            linha,
            text="Selecionar",
            width=120,
            command=self.selecionar
        ).pack(side="right")

        # LOGIN
        ctk.CTkLabel(frame, text="Login emissor").pack(anchor="w", pady=(15,0))

        self.entry_login = ctk.CTkEntry(frame)
        self.entry_login.pack(fill="x", pady=5)

        # SENHA
        ctk.CTkLabel(frame, text="Senha").pack(anchor="w", pady=(15,0))

        self.entry_senha = ctk.CTkEntry(frame, show="*")
        self.entry_senha.pack(fill="x", pady=5)

        # BOTÃO SALVAR
        ctk.CTkButton(
            frame,
            text="💾 Salvar Configuração",
            height=40,
            font=("Arial", 14, "bold"),
            command=self.salvar
        ).pack(pady=25)

    def selecionar(self):

        pasta = filedialog.askdirectory()

        if pasta:
            self.entry_caminho.delete(0, "end")
            self.entry_caminho.insert(0, pasta)

    def salvar(self):

        caminho = self.entry_caminho.get()
        login = self.entry_login.get()
        senha = self.entry_senha.get()

        if not caminho or not login or not senha:
            return

        salvar_config(caminho, login, senha)

        self.destroy()