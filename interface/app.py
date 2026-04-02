from tkinter import filedialog
from datetime import datetime
from pathlib import Path
from getpass import getuser
import threading
import queue
import traceback
import customtkinter as ctk

from database.db import criar_banco, primeiro_acesso, carregar_config
from interface.tela_config import TelaConfig
from dados.leitor_planilha import PlanilhaNotasRepository, montar_caminho_planilha
from automacao.robo_adapter import RoboEmissorNFSe
from utils.orquestrador_emissao import OrquestradorEmissao

from dados.leitor_planilha import PlanilhaNotasRepository
from dados.atualizador_planilha import AtualizadorPlanilha

import sys
from pathlib import Path

# garante raiz do projeto no path
sys.path.append(str(Path(__file__).resolve().parent.parent))


# ===============================
# TEMA
# ===============================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ===============================
# BANCO
# ===============================
criar_banco()

if primeiro_acesso():
    tela = TelaConfig()
    tela.mainloop()


# ===============================
# APP PRINCIPAL
# ===============================
class EmissorApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Emissor Automático de NFS-e")
        self.geometry("1200x750")

        # ===============================
        # CONFIGURAÇÕES
        # ===============================
        config = carregar_config()

        self.base_notas = config["caminho_base"]
        self.caminho_base = self.base_notas  # mantém compatibilidade
        
        self.login_prefeitura = config["login"]
        self.senha_prefeitura = config["senha"]

        print("CAMINHO BASE CONFIGURADO:", self.caminho_base)
        print("🔥 INIT RODANDO")
        print("BASE_NOTAS:", self.base_notas)

        self.usuario_logado = getuser()

        self.event_queue = queue.Queue()
        self.emissao_em_andamento = False

        self.criar_layout()

        self.after(150, self.processar_fila_eventos)

    # ===============================
    # LAYOUT
    # ===============================
    def criar_layout(self):

        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        sidebar.pack(side="left", fill="y")

        titulo = ctk.CTkLabel(
            sidebar,
            text="Emissor NFS-e",
            font=("Arial", 22, "bold")
        )
        titulo.pack(pady=30)

        ctk.CTkButton(sidebar, text="Emitir Notas").pack(pady=10, padx=25)
        ctk.CTkButton(sidebar, text="Histórico").pack(pady=10, padx=25)
        ctk.CTkButton(sidebar, text="Configurações").pack(pady=10, padx=25)

        main = ctk.CTkFrame(self)
        main.pack(side="left", fill="both", expand=True, padx=15, pady=15)

        # ===============================
        # DASHBOARD
        # ===============================
        dash = ctk.CTkFrame(main)
        dash.pack(fill="x", pady=10)

        self.card(dash, "📄 Notas Pendentes", "0").pack(side="left", padx=10)
        self.card(dash, "💰 Valor Total", "0").pack(side="left", padx=10)
        self.card(dash, "✔ Emitidas Hoje", "0").pack(side="left", padx=10)

        # ===============================
        # CONFIG
        # ===============================
        config = ctk.CTkFrame(main)
        config.pack(fill="x", pady=10)

        ctk.CTkLabel(
            config,
            text="⚙ Configuração de Emissão",
            font=("Arial", 18, "bold")
        ).pack(anchor="w", padx=15, pady=15)

        # PERÍODO
        ctk.CTkLabel(config, text="Período").pack(anchor="w", padx=15)

        periodo = ctk.CTkFrame(config, fg_color="transparent")
        periodo.pack(fill="x", padx=15)

        self.combo_ano = ctk.CTkComboBox(
            periodo,
            width=120,
            values=["2024", "2025", "2026", "2027"]
        )
        self.combo_ano.set("2026")
        self.combo_ano.pack(side="left", padx=5)

        self.combo_mes = ctk.CTkComboBox(
            periodo,
            width=180,
            values=[
                "01 - Janeiro","02 - Fevereiro","03 - Março",
                "04 - Abril","05 - Maio","06 - Junho",
                "07 - Julho","08 - Agosto","09 - Setembro",
                "10 - Outubro","11 - Novembro","12 - Dezembro"
            ]
        )
        self.combo_mes.set("02 - Fevereiro")
        self.combo_mes.pack(side="left", padx=5)

        # CAMPOS
        linha_campos = ctk.CTkFrame(config, fg_color="transparent")
        linha_campos.pack(fill="x", padx=15, pady=10)

        self.combo_municipio = ctk.CTkComboBox(
            linha_campos,
            values=[
                "Afogados da Ingazeira",
                "Triunfo",
                "Serra Talhada"
            ]
        )
        self.combo_municipio.pack(side="left", expand=True, fill="x", padx=5)

        self.combo_secretaria = ctk.CTkComboBox(
            linha_campos,
            values=["Todas","Saúde","Educação","Assistência"]
        )
        self.combo_secretaria.pack(side="left", expand=True, fill="x", padx=5)

        self.combo_especie = ctk.CTkComboBox(
            linha_campos,
            values=["Todas","Reembolso","Lote I","Lote II","Avulsa"]
        )
        self.combo_especie.pack(side="left", expand=True, fill="x", padx=5)

        # MODO
        self.modo = ctk.StringVar(value="todas")

        ctk.CTkRadioButton(config, text="Emitir todas", variable=self.modo, value="todas").pack(anchor="w", padx=15)
        ctk.CTkRadioButton(config, text="Por item", variable=self.modo, value="item").pack(anchor="w", padx=15)
        ctk.CTkRadioButton(config, text="Teste", variable=self.modo, value="teste").pack(anchor="w", padx=15)

        self.entry_itens = ctk.CTkEntry(config)
        self.entry_itens.pack(fill="x", padx=15, pady=10)

        # BOTÃO
        self.botao_emitir = ctk.CTkButton(
            config,
            text="🚀 INICIAR EMISSÃO DE NOTAS",
            command=self.iniciar_emissao
        )
        self.botao_emitir.pack(pady=20)

        # PROGRESSO
        self.progress = ctk.CTkProgressBar(main)
        self.progress.pack(fill="x", padx=10)
        self.progress.set(0)

        self.label_progresso = ctk.CTkLabel(main, text="0 / 0 notas")
        self.label_progresso.pack(anchor="w", padx=10)

        # LOG
        self.log = ctk.CTkTextbox(main)
        self.log.pack(fill="both", expand=True, padx=10, pady=10)

    def card(self,parent,titulo,valor):
        frame = ctk.CTkFrame(parent,width=250,height=110)
        frame.pack_propagate(False)
        ctk.CTkLabel(frame,text=titulo).pack(pady=(20,5))
        ctk.CTkLabel(frame,text=valor,font=("Arial",28,"bold")).pack()
        return frame

    def logar(self,texto):
        agora = datetime.now().strftime("%H:%M:%S")
        self.log.insert("end",f"[{agora}] {texto}\n")
        self.log.see("end")

    def processar_fila_eventos(self):

        try:

            while True:

                evento = self.event_queue.get_nowait()

                if evento[0]=="log":
                    self.logar(evento[1])

                elif evento[0]=="progress":

                    atual,total = evento[1],evento[2]

                    percentual = atual/total if total>0 else 0

                    self.progress.set(percentual)

                    self.label_progresso.configure(
                        text=f"{atual} / {total} notas"
                    )

                elif evento[0]=="finish":

                    self.logar("Processo finalizado")

                    self.botao_emitir.configure(state="normal")

                    self.emissao_em_andamento = False  # 🔥 IMPORTANTE

        except queue.Empty:
            pass

        self.after(150,self.processar_fila_eventos)

    # ===============================
    # BOTÃO
    # ===============================
    def iniciar_emissao(self):

        print("BOTÃO INICIAR EMISSÃO CLICADO")

        if self.emissao_em_andamento:
            self.logar("⚠ Já existe uma emissão em andamento.")
            return

        self.emissao_em_andamento = True
        self.botao_emitir.configure(state="disabled")

        self.progress.set(0)
        self.label_progresso.configure(text="0 / 0 notas")

        self.logar("🚀 Iniciando processo de emissão")

        ano = self.combo_ano.get()
        mes = self.combo_mes.get()
        municipio = self.combo_municipio.get()

        print("ANO:", ano)
        print("MES:", mes)
        print("MUNICIPIO:", municipio)

        secretaria = self.combo_secretaria.get()
        especie = self.combo_especie.get()

        modo = self.modo.get()

        itens = None

        # ==========================
        # ITENS (SÓ DEPENDE DO MODO)
        # ==========================
        if modo in ["item", "teste"]:

            texto = self.entry_itens.get().strip()

            if texto:
                itens = [i.strip() for i in texto.split(",")]

        # ==========================
        # 🔥 CAMINHO PLANILHA (FORA DO IF)
        # ==========================
        caminho_planilha = montar_caminho_planilha(
            self.base_notas,
            ano,
            mes,
            municipio
        )

        print("CAMINHO PLANILHA:", caminho_planilha)
        self.logar(f"📄 Planilha localizada: {caminho_planilha}")

        thread = threading.Thread(
            target=self.executar_emissao_thread,
            args=(caminho_planilha, secretaria, especie, itens),
            daemon=True
        )

        thread.start()

    # ===============================
    # THREAD
    # ===============================


    def executar_emissao_thread(self, caminho_planilha, secretaria, especie, itens):

        print("THREAD DE EMISSÃO INICIADA")
        print("PLANILHA RECEBIDA:", caminho_planilha)

        try:

            self.event_queue.put(("log", "📦 Carregando planilha..."))

            # ===============================
            # NOVO PADRÃO (V2)
            # ===============================
            leitor = PlanilhaNotasRepository(caminho_planilha)

            # 🔥 o próprio leitor atualiza também
            atualizador = leitor

            self.event_queue.put(("log", "⚙️ Preparando orquestrador..."))
            
            orquestrador = OrquestradorEmissao(                
                leitor_planilha=leitor,
                atualizador_planilha=atualizador,
                log_callback=lambda msg: self.event_queue.put(("log", msg)),
                progresso_callback=lambda atual, total: self.event_queue.put(("progress", atual, total)),
                finish_callback=None
            )

            self.event_queue.put(("log", "🚀 Iniciando execução..."))

            # ===============================
            # FILTROS
            # ===============================
            filtros = {
                "ano": self.combo_ano.get(),
                "mes": self.combo_mes.get(),
                "municipio": self.combo_municipio.get(),
                "secretaria": secretaria,
                "especie": especie,
                "modo_emissao": self.modo.get(),
                "item": itens[0] if itens else ""
            }

            orquestrador.executar(
                caminho_planilha=caminho_planilha,
                filtros=filtros,
                headless=False
            )

            self.event_queue.put(("log", "✅ Execução finalizada com sucesso"))
            self.event_queue.put(("log", "🔥 CHEGUEI NO ENVIO"))


        except Exception as e:

            print("\n❌ ERRO COMPLETO NA THREAD:")
            traceback.print_exc()

            self.event_queue.put(("log", f"❌ Erro geral: {str(e)}"))

        finally:

            self.event_queue.put(("finish",))
            self.emissao_em_andamento = False


# ===============================
# EXECUTAR
# ===============================
if __name__ == "__main__":
    app = EmissorApp()
    app.mainloop()