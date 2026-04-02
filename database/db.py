import sqlite3


# ==========================================
# CRIAR BANCO
# ==========================================
def criar_banco():

    conn = sqlite3.connect("config.db")

    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS config (

        id INTEGER PRIMARY KEY AUTOINCREMENT,
        caminho_base TEXT,
        login TEXT,
        senha TEXT
    )
    """)

    conn.commit()
    conn.close()


# ==========================================
# PRIMEIRO ACESSO
# ==========================================
def primeiro_acesso():

    conn = sqlite3.connect("config.db")

    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM config")

    total = cursor.fetchone()[0]

    conn.close()

    return total == 0


# ==========================================
# SALVAR CONFIG
# ==========================================
def salvar_config(caminho_base, login, senha):

    conn = sqlite3.connect("config.db")

    cursor = conn.cursor()

    cursor.execute("DELETE FROM config")

    cursor.execute(
        "INSERT INTO config (caminho_base, login, senha) VALUES (?, ?, ?)",
        (caminho_base, login, senha)
    )

    conn.commit()
    conn.close()


# ==========================================
# CARREGAR CONFIG
# ==========================================
def carregar_config():

    conn = sqlite3.connect("config.db")

    cursor = conn.cursor()

    cursor.execute("SELECT caminho_base, login, senha FROM config LIMIT 1")

    row = cursor.fetchone()

    conn.close()

    if row:
        return {
            "caminho_base": row[0],
            "login": row[1],
            "senha": row[2]
        }

    return {
        "caminho_base": "",
        "login": "",
        "senha": ""
    }