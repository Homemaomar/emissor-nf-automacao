import customtkinter as ctk

from database.db import listar_notas_importadas, obter_nota_importada


class NotaDetalheWindow(ctk.CTkToplevel):
    def __init__(self, parent, nota_id):
        super().__init__(parent)

        self.title("Detalhes da nota")
        self.geometry("760x720")
        self.configure(fg_color="#f4f1ea")
        self.transient(parent)
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(250, lambda: self.attributes("-topmost", False))

        nota = obter_nota_importada(nota_id)
        self._criar_layout(nota or {})

    def _criar_layout(self, nota):
        frame = ctk.CTkScrollableFrame(
            self,
            fg_color="#ffffff",
            corner_radius=24,
            border_width=1,
            border_color="#ddd4c8",
        )
        frame.pack(fill="both", expand=True, padx=24, pady=24)

        ctk.CTkLabel(
            frame,
            text=nota.get("cliente_nome") or "Nota sem cliente identificado",
            font=("Segoe UI Semibold", 24, "bold"),
            text_color="#1f1f1c",
        ).pack(anchor="w", padx=20, pady=(20, 8))

        campos = [
            ("Origem", f"{nota.get('source_type', '').upper()} | {nota.get('source_file', '')}"),
            ("Documento", nota.get("cliente_documento", "")),
            ("Email", nota.get("cliente_email", "")),
            ("Descricao", nota.get("descricao", "")),
            ("Valor", f"R$ {float(nota.get('valor_servico', 0) or 0):,.2f}"),
            ("Municipio", nota.get("municipio", "")),
            ("CTN", nota.get("ctn", "")),
            ("NBS", nota.get("nbs", "")),
            ("Competencia", f"{nota.get('competencia_mes', '')}/{nota.get('competencia_ano', '')}"),
            ("Recorrencia", f"{nota.get('recorrente_score', 0)}%"),
            ("Status", nota.get("status_exibicao") or nota.get("status", "")),
            ("Importado por", nota.get("imported_by_name", "")),
            ("Importado em", nota.get("imported_at", "")),
        ]

        for titulo, valor in campos:
            bloco = ctk.CTkFrame(
                frame,
                fg_color="#f7f4ee",
                corner_radius=18,
                border_width=1,
                border_color="#ddd4c8",
            )
            bloco.pack(fill="x", padx=20, pady=8)

            ctk.CTkLabel(
                bloco,
                text=titulo,
                font=("Segoe UI Semibold", 13, "bold"),
                text_color="#6d675f",
            ).pack(anchor="w", padx=16, pady=(14, 4))

            ctk.CTkLabel(
                bloco,
                text=str(valor or "-"),
                font=("Segoe UI", 13),
                text_color="#1f1f1c",
                justify="left",
                wraplength=640,
            ).pack(anchor="w", padx=16, pady=(0, 14))


class NotasBancoWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)

        self.detail_window = None
        self.title("Notas no banco")
        self.geometry("980x720")
        self.configure(fg_color="#f4f1ea")
        self.transient(parent)
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(250, lambda: self.attributes("-topmost", False))

        self._criar_layout()
        self.recarregar()

    def _criar_layout(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hero = ctk.CTkFrame(
            self,
            fg_color="#ffffff",
            corner_radius=24,
            border_width=1,
            border_color="#ddd4c8",
        )
        hero.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 18))

        ctk.CTkLabel(
            hero,
            text="Notas importadas no banco",
            font=("Segoe UI Semibold", 28, "bold"),
            text_color="#1f1f1c",
        ).pack(anchor="w", padx=20, pady=(20, 6))

        ctk.CTkLabel(
            hero,
            text="Clique em uma nota para visualizar todos os dados importados.",
            font=("Segoe UI", 13),
            text_color="#6d675f",
        ).pack(anchor="w", padx=20, pady=(0, 18))

        self.lista = ctk.CTkScrollableFrame(
            self,
            fg_color="#ffffff",
            corner_radius=24,
            border_width=1,
            border_color="#ddd4c8",
        )
        self.lista.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 24))

    def recarregar(self):
        for child in self.lista.winfo_children():
            child.destroy()

        notas = listar_notas_importadas(limit=100)
        if not notas:
            ctk.CTkLabel(
                self.lista,
                text="Nenhuma nota importada encontrada.",
                font=("Segoe UI", 14),
                text_color="#6d675f",
            ).pack(anchor="w", padx=20, pady=20)
            return

        for nota in notas:
            card = ctk.CTkFrame(
                self.lista,
                fg_color="#f7f4ee",
                corner_radius=18,
                border_width=1,
                border_color="#ddd4c8",
            )
            card.pack(fill="x", padx=14, pady=8)

            titulo = nota.get("cliente_nome") or "Sem cliente identificado"
            status = nota.get("status_exibicao") or nota.get("status") or "Sem status"
            descricao = nota.get("descricao") or "Sem descricao"
            valor = float(nota.get("valor_servico", 0) or 0)

            ctk.CTkLabel(
                card,
                text=f"{titulo} | {status}",
                font=("Segoe UI Semibold", 15, "bold"),
                text_color="#1f1f1c",
            ).pack(anchor="w", padx=16, pady=(16, 4))

            ctk.CTkLabel(
                card,
                text=f"{descricao[:140]}{'...' if len(descricao) > 140 else ''}",
                font=("Segoe UI", 12),
                text_color="#6d675f",
                justify="left",
                wraplength=720,
            ).pack(anchor="w", padx=16, pady=(0, 10))

            rodape = ctk.CTkFrame(card, fg_color="transparent")
            rodape.pack(fill="x", padx=16, pady=(0, 16))

            ctk.CTkLabel(
                rodape,
                text=f"Valor: R$ {valor:,.2f} | Tipo: {nota.get('source_type', '').upper()}",
                font=("Segoe UI", 12),
                text_color="#948b80",
            ).pack(side="left")

            ctk.CTkButton(
                rodape,
                text="Visualizar",
                width=110,
                height=34,
                fg_color="#b77931",
                hover_color="#9e6528",
                text_color="#fffaf4",
                command=lambda nid=nota["id"]: self._abrir_detalhe(nid),
            ).pack(side="right")

    def _abrir_detalhe(self, nota_id):
        if self.detail_window is not None and self.detail_window.winfo_exists():
            self.detail_window.destroy()
        self.detail_window = NotaDetalheWindow(self, nota_id)
