import hashlib
import hmac
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


DB_PATH = Path("config.db")
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PLANS_DEFAULT = (
    {
        "code": "emissor",
        "nome": "Emissor",
        "valor_mensal": 180.0,
        "recursos": ["emissao_nfse"],
    },
    {
        "code": "emissor_email",
        "nome": "Emissor + Email",
        "valor_mensal": 250.0,
        "recursos": ["emissao_nfse", "envio_email"],
    },
    {
        "code": "emissor_email_whatsapp",
        "nome": "Emissor + Email + WhatsApp",
        "valor_mensal": 280.0,
        "recursos": ["emissao_nfse", "envio_email", "envio_whatsapp"],
    },
)
BILLING_ACTIVE_STATUSES = {"trial", "active", "paid", "development"}
BILLING_BLOCKED_STATUSES = {"blocked", "suspended", "cancelled"}


def _connect():
    return sqlite3.connect(DB_PATH)


def _dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def _normalizar_email(email):
    return (email or "").strip().lower()


def _validar_email(email):
    if not EMAIL_REGEX.match(email):
        raise ValueError("Informe um email valido para o acesso.")


def _ensure_column(cursor, table_name, column_name, definition):
    cursor.execute(f"PRAGMA table_info({table_name})")
    colunas = {row[1] for row in cursor.fetchall()}
    if column_name not in colunas:
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )


def _utc_now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _parse_iso_datetime(value):
    texto = str(value or "").strip()
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


def _seed_planos(cursor):
    agora = _utc_now_iso()
    for plano in PLANS_DEFAULT:
        cursor.execute(
            """
            INSERT INTO planos_cobranca (
                code,
                nome,
                valor_mensal,
                recursos_json,
                ativo,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                nome = excluded.nome,
                valor_mensal = excluded.valor_mensal,
                recursos_json = excluded.recursos_json,
                updated_at = excluded.updated_at
            """,
            (
                plano["code"],
                plano["nome"],
                float(plano.get("valor_mensal", 0) or 0),
                json.dumps(plano.get("recursos", []), ensure_ascii=True),
                agora,
                agora,
            ),
        )


def _garantir_assinatura_sistema(cursor):
    cursor.execute("SELECT COUNT(*) FROM assinatura_sistema")
    total = cursor.fetchone()[0]
    if total:
        return

    agora = datetime.now()
    cursor.execute(
        """
        INSERT INTO assinatura_sistema (
            plano_code,
            status,
            ciclo,
            started_at,
            next_due_at,
            grace_until,
            billing_contact_name,
            billing_contact_email,
            observacoes,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "emissor_email_whatsapp",
            "development",
            "mensal",
            agora.isoformat(timespec="seconds"),
            "",
            "",
            "",
            "",
            "Assinatura inicial criada automaticamente para desenvolvimento.",
            agora.isoformat(timespec="seconds"),
        ),
    )


def _hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        120000,
    )
    return salt.hex(), digest.hex()


def _verificar_password(password, salt_hex, hash_hex):
    salt = bytes.fromhex(salt_hex)
    _, novo_hash = _hash_password(password, salt=salt)
    return hmac.compare_digest(novo_hash, hash_hex)


def criar_banco():
    conn = _connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caminho_base TEXT,
            login TEXT,
            senha TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'operador',
            ativo INTEGER NOT NULL DEFAULT 1,
            approval_status TEXT NOT NULL DEFAULT 'approved',
            approved_by INTEGER,
            approved_at TEXT,
            created_at TEXT NOT NULL,
            last_login_at TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS emissoes_auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            usuario_nome TEXT,
            role TEXT,
            item TEXT,
            status TEXT,
            numero_nfse TEXT,
            caminho_planilha TEXT,
            municipio TEXT,
            ano TEXT,
            mes TEXT,
            excel_row INTEGER,
            mensagem TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS notas_importadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_file TEXT NOT NULL,
            source_ref TEXT NOT NULL DEFAULT '',
            cliente_nome TEXT,
            cliente_documento TEXT,
            cliente_email TEXT,
            descricao TEXT,
            valor_servico REAL DEFAULT 0,
            ir REAL DEFAULT 0,
            iss REAL DEFAULT 0,
            municipio TEXT,
            ctn TEXT,
            nbs TEXT,
            competencia_ano TEXT,
            competencia_mes TEXT,
            recorrente_key TEXT,
            recorrente_score INTEGER DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'IMPORTADA',
            payload_json TEXT,
            imported_by INTEGER,
            imported_by_name TEXT,
            imported_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_type, source_file, source_ref)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS modelos_recorrentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_modelo TEXT NOT NULL,
            cliente_nome TEXT,
            cliente_documento TEXT,
            cliente_email TEXT,
            descricao TEXT,
            valor_servico REAL DEFAULT 0,
            ir REAL DEFAULT 0,
            iss REAL DEFAULT 0,
            municipio TEXT,
            ctn TEXT,
            nbs TEXT,
            periodicidade TEXT NOT NULL DEFAULT 'mensal',
            ativo INTEGER NOT NULL DEFAULT 1,
            origem_nota_id INTEGER,
            recorrente_key TEXT,
            criado_por INTEGER,
            criado_por_nome TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(origem_nota_id) REFERENCES notas_importadas(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS planos_cobranca (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            valor_mensal REAL NOT NULL DEFAULT 0,
            recursos_json TEXT NOT NULL DEFAULT '[]',
            ativo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS assinatura_sistema (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plano_code TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'development',
            ciclo TEXT NOT NULL DEFAULT 'mensal',
            started_at TEXT,
            next_due_at TEXT,
            grace_until TEXT,
            billing_contact_name TEXT,
            billing_contact_email TEXT,
            observacoes TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(plano_code) REFERENCES planos_cobranca(code)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cobrancas_mensais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assinatura_id INTEGER,
            referencia_ano INTEGER NOT NULL,
            referencia_mes INTEGER NOT NULL,
            plano_code TEXT NOT NULL,
            valor REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pendente',
            due_at TEXT,
            paid_at TEXT,
            payment_method TEXT,
            external_ref TEXT,
            observacoes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(referencia_ano, referencia_mes, plano_code),
            FOREIGN KEY(assinatura_id) REFERENCES assinatura_sistema(id),
            FOREIGN KEY(plano_code) REFERENCES planos_cobranca(code)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS portal_clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            telefone TEXT,
            documento TEXT,
            endereco TEXT,
            ativo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_login_at TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS portal_assinaturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            plano_code TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'checkout',
            ciclo TEXT NOT NULL DEFAULT 'mensal',
            started_at TEXT,
            next_due_at TEXT,
            cancelled_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(cliente_id) REFERENCES portal_clientes(id),
            FOREIGN KEY(plano_code) REFERENCES planos_cobranca(code)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS portal_cobrancas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assinatura_id INTEGER NOT NULL,
            cliente_id INTEGER NOT NULL,
            plano_code TEXT NOT NULL,
            referencia_ano INTEGER NOT NULL,
            referencia_mes INTEGER NOT NULL,
            valor REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pendente',
            payment_method TEXT,
            due_at TEXT,
            paid_at TEXT,
            checkout_token TEXT,
            external_ref TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(assinatura_id) REFERENCES portal_assinaturas(id),
            FOREIGN KEY(cliente_id) REFERENCES portal_clientes(id),
            FOREIGN KEY(plano_code) REFERENCES planos_cobranca(code)
        )
        """
    )

    _ensure_column(cursor, "config", "recurrence_enabled", "INTEGER DEFAULT 0")
    _ensure_column(cursor, "config", "recurrence_frequency", "TEXT DEFAULT 'manual'")
    _ensure_column(cursor, "config", "notification_email", "TEXT DEFAULT ''")
    _ensure_column(cursor, "config", "smtp_sender_email", "TEXT DEFAULT ''")
    _ensure_column(cursor, "config", "smtp_sender_password", "TEXT DEFAULT ''")
    _ensure_column(cursor, "usuarios", "approval_status", "TEXT DEFAULT 'approved'")
    _ensure_column(cursor, "usuarios", "approved_by", "INTEGER")
    _ensure_column(cursor, "usuarios", "approved_at", "TEXT")
    _ensure_column(cursor, "notas_importadas", "recorrente_key", "TEXT")
    _ensure_column(cursor, "notas_importadas", "recorrente_score", "INTEGER DEFAULT 0")
    _ensure_column(cursor, "notas_importadas", "source_ref", "TEXT NOT NULL DEFAULT ''")

    _seed_planos(cursor)
    _garantir_assinatura_sistema(cursor)

    cursor.execute(
        """
        UPDATE usuarios
        SET approval_status = 'approved'
        WHERE approval_status IS NULL OR approval_status = ''
        """
    )

    conn.commit()
    conn.close()


def primeiro_acesso():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM config")
    total = cursor.fetchone()[0]
    conn.close()
    return total == 0


def salvar_config(
    caminho_base,
    login,
    senha,
    recurrence_enabled=False,
    recurrence_frequency="manual",
    notification_email="",
    smtp_sender_email="",
    smtp_sender_password="",
):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM config")
    cursor.execute(
        """
        INSERT INTO config (
            caminho_base,
            login,
            senha,
            recurrence_enabled,
            recurrence_frequency,
            notification_email,
            smtp_sender_email,
            smtp_sender_password
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            caminho_base,
            login,
            senha,
            int(bool(recurrence_enabled)),
            recurrence_frequency,
            notification_email,
            smtp_sender_email,
            smtp_sender_password,
        ),
    )
    conn.commit()
    conn.close()


def carregar_config():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            caminho_base,
            login,
            senha,
            COALESCE(recurrence_enabled, 0),
            COALESCE(recurrence_frequency, 'manual'),
            COALESCE(notification_email, ''),
            COALESCE(smtp_sender_email, ''),
            COALESCE(smtp_sender_password, '')
        FROM config
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "caminho_base": row[0] or "",
            "login": row[1] or "",
            "senha": row[2] or "",
            "recurrence_enabled": bool(row[3]),
            "recurrence_frequency": row[4] or "manual",
            "notification_email": row[5] or "",
            "smtp_sender_email": row[6] or "",
            "smtp_sender_password": row[7] or "",
        }

    return {
        "caminho_base": "",
        "login": "",
        "senha": "",
        "recurrence_enabled": False,
        "recurrence_frequency": "manual",
        "notification_email": "",
        "smtp_sender_email": "",
        "smtp_sender_password": "",
    }


def contar_usuarios():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    total = cursor.fetchone()[0]
    conn.close()
    return total


def listar_planos_cobranca(apenas_ativos=True):
    conn = _connect()
    conn.row_factory = _dict_factory
    cursor = conn.cursor()

    query = """
        SELECT code, nome, valor_mensal, recursos_json, ativo, created_at, updated_at
        FROM planos_cobranca
    """
    params = ()
    if apenas_ativos:
        query += " WHERE ativo = 1"
    query += " ORDER BY id ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        try:
            row["recursos"] = json.loads(row.get("recursos_json") or "[]")
        except Exception:
            row["recursos"] = []
    return rows


def obter_assinatura_sistema():
    conn = _connect()
    conn.row_factory = _dict_factory
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            a.id,
            a.plano_code,
            a.status,
            a.ciclo,
            a.started_at,
            a.next_due_at,
            a.grace_until,
            a.billing_contact_name,
            a.billing_contact_email,
            a.observacoes,
            a.updated_at,
            p.nome AS plano_nome,
            p.valor_mensal,
            p.recursos_json
        FROM assinatura_sistema a
        LEFT JOIN planos_cobranca p ON p.code = a.plano_code
        ORDER BY a.id DESC
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    try:
        row["recursos"] = json.loads(row.get("recursos_json") or "[]")
    except Exception:
        row["recursos"] = []
    return row


def salvar_assinatura_sistema(
    plano_code,
    status="active",
    ciclo="mensal",
    started_at="",
    next_due_at="",
    grace_until="",
    billing_contact_name="",
    billing_contact_email="",
    observacoes="",
):
    plano_code = str(plano_code or "").strip()
    if not plano_code:
        raise ValueError("Informe um plano valido para a assinatura.")

    if billing_contact_email:
        _validar_email(_normalizar_email(billing_contact_email))

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM planos_cobranca WHERE code = ?",
        (plano_code,),
    )
    if cursor.fetchone()[0] == 0:
        conn.close()
        raise ValueError("Plano informado nao existe.")

    cursor.execute("SELECT id FROM assinatura_sistema ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    assinatura_id = row[0] if row else None
    agora = _utc_now_iso()

    params = (
        plano_code,
        str(status or "active").strip().lower(),
        str(ciclo or "mensal").strip().lower(),
        started_at or "",
        next_due_at or "",
        grace_until or "",
        str(billing_contact_name or "").strip(),
        _normalizar_email(billing_contact_email) if billing_contact_email else "",
        str(observacoes or "").strip(),
        agora,
    )

    if assinatura_id:
        cursor.execute(
            """
            UPDATE assinatura_sistema
            SET
                plano_code = ?,
                status = ?,
                ciclo = ?,
                started_at = ?,
                next_due_at = ?,
                grace_until = ?,
                billing_contact_name = ?,
                billing_contact_email = ?,
                observacoes = ?,
                updated_at = ?
            WHERE id = ?
            """,
            params + (assinatura_id,),
        )
    else:
        cursor.execute(
            """
            INSERT INTO assinatura_sistema (
                plano_code,
                status,
                ciclo,
                started_at,
                next_due_at,
                grace_until,
                billing_contact_name,
                billing_contact_email,
                observacoes,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )
        assinatura_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return assinatura_id


def registrar_cobranca_mensal(
    referencia_ano,
    referencia_mes,
    plano_code,
    valor,
    status="pendente",
    due_at="",
    paid_at="",
    payment_method="",
    external_ref="",
    observacoes="",
):
    assinatura = obter_assinatura_sistema()
    assinatura_id = assinatura.get("id") if assinatura else None
    agora = _utc_now_iso()

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO cobrancas_mensais (
            assinatura_id,
            referencia_ano,
            referencia_mes,
            plano_code,
            valor,
            status,
            due_at,
            paid_at,
            payment_method,
            external_ref,
            observacoes,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(referencia_ano, referencia_mes, plano_code)
        DO UPDATE SET
            assinatura_id = excluded.assinatura_id,
            valor = excluded.valor,
            status = excluded.status,
            due_at = excluded.due_at,
            paid_at = excluded.paid_at,
            payment_method = excluded.payment_method,
            external_ref = excluded.external_ref,
            observacoes = excluded.observacoes,
            updated_at = excluded.updated_at
        """,
        (
            assinatura_id,
            int(referencia_ano),
            int(referencia_mes),
            plano_code,
            float(valor or 0),
            str(status or "pendente").strip().lower(),
            due_at or "",
            paid_at or "",
            str(payment_method or "").strip(),
            str(external_ref or "").strip(),
            str(observacoes or "").strip(),
            agora,
            agora,
        ),
    )
    conn.commit()
    conn.close()


def gerar_cobranca_mensal_atual():
    assinatura = obter_assinatura_sistema()
    if not assinatura:
        raise ValueError("Assinatura do sistema nao encontrada.")

    agora = datetime.now()
    proximo_vencimento = (
        assinatura.get("next_due_at")
        or datetime(agora.year, agora.month, 10).isoformat(timespec="seconds")
    )

    registrar_cobranca_mensal(
        referencia_ano=agora.year,
        referencia_mes=agora.month,
        plano_code=assinatura.get("plano_code", "emissor"),
        valor=assinatura.get("valor_mensal", 0) or 0,
        status="pendente",
        due_at=proximo_vencimento,
        observacoes="Cobranca gerada automaticamente para a competencia atual.",
    )


def listar_cobrancas_mensais(limit=24):
    conn = _connect()
    conn.row_factory = _dict_factory
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            c.id,
            c.assinatura_id,
            c.referencia_ano,
            c.referencia_mes,
            c.plano_code,
            c.valor,
            c.status,
            c.due_at,
            c.paid_at,
            c.payment_method,
            c.external_ref,
            c.observacoes,
            c.created_at,
            c.updated_at,
            p.nome AS plano_nome
        FROM cobrancas_mensais c
        LEFT JOIN planos_cobranca p ON p.code = c.plano_code
        ORDER BY c.referencia_ano DESC, c.referencia_mes DESC, c.id DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def atualizar_status_cobranca(
    cobranca_id,
    status,
    paid_at="",
    payment_method="",
    external_ref="",
    observacoes="",
):
    conn = _connect()
    cursor = conn.cursor()
    agora = _utc_now_iso()
    status_normalizado = str(status or "").strip().lower()
    pago_em = paid_at or (_utc_now_iso() if status_normalizado == "pago" else "")

    cursor.execute(
        """
        UPDATE cobrancas_mensais
        SET
            status = ?,
            paid_at = ?,
            payment_method = ?,
            external_ref = ?,
            observacoes = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            status_normalizado,
            pago_em,
            str(payment_method or "").strip(),
            str(external_ref or "").strip(),
            str(observacoes or "").strip(),
            agora,
            int(cobranca_id),
        ),
    )
    conn.commit()
    conn.close()


def obter_recursos_assinatura():
    assinatura = obter_assinatura_sistema()
    if not assinatura:
        return []
    return assinatura.get("recursos", [])


def criar_cliente_portal(nome, email, password, telefone="", documento="", endereco=""):
    nome = str(nome or "").strip()
    email = _normalizar_email(email)
    password = password or ""

    if not nome or not email or not password:
        raise ValueError("Nome, email e senha sao obrigatorios.")

    _validar_email(email)

    if len(password) < 4:
        raise ValueError("A senha precisa ter pelo menos 4 caracteres.")

    salt_hex, hash_hex = _hash_password(password)
    agora = _utc_now_iso()

    conn = _connect()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO portal_clientes (
                nome,
                email,
                password_salt,
                password_hash,
                telefone,
                documento,
                endereco,
                ativo,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                nome,
                email,
                salt_hex,
                hash_hex,
                str(telefone or "").strip(),
                str(documento or "").strip(),
                str(endereco or "").strip(),
                agora,
            ),
        )
        cliente_id = cursor.lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError("Ja existe um cliente com esse email.") from exc
    finally:
        conn.commit()
        conn.close()

    return obter_cliente_portal(cliente_id)


def obter_cliente_portal(cliente_id):
    conn = _connect()
    conn.row_factory = _dict_factory
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            nome,
            email,
            telefone,
            documento,
            endereco,
            ativo,
            created_at,
            last_login_at
        FROM portal_clientes
        WHERE id = ?
        LIMIT 1
        """,
        (int(cliente_id),),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def autenticar_cliente_portal(email, password):
    email = _normalizar_email(email)
    password = password or ""

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            nome,
            email,
            password_salt,
            password_hash,
            ativo,
            telefone,
            documento,
            endereco,
            created_at,
            last_login_at
        FROM portal_clientes
        WHERE email = ?
        LIMIT 1
        """,
        (email,),
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"ok": False, "reason": "invalid_credentials"}

    (
        cliente_id,
        nome,
        cliente_email,
        salt_hex,
        hash_hex,
        ativo,
        telefone,
        documento,
        endereco,
        created_at,
        last_login_at,
    ) = row

    if not _verificar_password(password, salt_hex, hash_hex):
        conn.close()
        return {"ok": False, "reason": "invalid_credentials"}

    if not ativo:
        conn.close()
        return {"ok": False, "reason": "inactive_user"}

    agora = _utc_now_iso()
    cursor.execute(
        "UPDATE portal_clientes SET last_login_at = ? WHERE id = ?",
        (agora, cliente_id),
    )
    conn.commit()
    conn.close()

    return {
        "ok": True,
        "cliente": {
            "id": cliente_id,
            "nome": nome,
            "email": cliente_email,
            "telefone": telefone or "",
            "documento": documento or "",
            "endereco": endereco or "",
            "created_at": created_at or "",
            "last_login_at": agora,
        },
    }


def iniciar_checkout_portal(cliente_id, plano_code, payment_method=""):
    assinatura = obter_assinatura_portal_ativa(cliente_id, incluir_checkout=True)
    agora = datetime.now()
    inicio = agora.isoformat(timespec="seconds")
    vencimento = (agora + timedelta(days=3)).isoformat(timespec="seconds")

    conn = _connect()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT nome, valor_mensal FROM planos_cobranca WHERE code = ? LIMIT 1",
        (plano_code,),
    )
    plano = cursor.fetchone()
    if not plano:
        conn.close()
        raise ValueError("Plano escolhido nao existe.")

    valor_plano = float(plano[1] or 0)

    if assinatura and assinatura.get("plano_code") == plano_code and assinatura.get("status") in {"checkout", "active", "paid"}:
        assinatura_id = assinatura["id"]
        cursor.execute(
            """
            UPDATE portal_assinaturas
            SET updated_at = ?, status = CASE WHEN status = 'cancelled' THEN 'checkout' ELSE status END
            WHERE id = ?
            """,
            (inicio, assinatura_id),
        )
    else:
        cursor.execute(
            """
            INSERT INTO portal_assinaturas (
                cliente_id,
                plano_code,
                status,
                ciclo,
                started_at,
                next_due_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, 'checkout', 'mensal', ?, ?, ?, ?)
            """,
            (int(cliente_id), plano_code, inicio, vencimento, inicio, inicio),
        )
        assinatura_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT INTO portal_cobrancas (
            assinatura_id,
            cliente_id,
            plano_code,
            referencia_ano,
            referencia_mes,
            valor,
            status,
            payment_method,
            due_at,
            checkout_token,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'pendente', ?, ?, ?, ?, ?)
        """,
        (
            assinatura_id,
            int(cliente_id),
            plano_code,
            agora.year,
            agora.month,
            valor_plano,
            str(payment_method or "").strip().lower(),
            vencimento,
            os.urandom(12).hex(),
            inicio,
            inicio,
        ),
    )
    cobranca_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return obter_checkout_portal(cobranca_id)


def obter_checkout_portal(cobranca_id):
    conn = _connect()
    conn.row_factory = _dict_factory
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            c.*,
            p.nome AS plano_nome,
            p.valor_mensal,
            pc.nome AS cliente_nome,
            pc.email AS cliente_email
        FROM portal_cobrancas c
        JOIN planos_cobranca p ON p.code = c.plano_code
        JOIN portal_clientes pc ON pc.id = c.cliente_id
        WHERE c.id = ?
        LIMIT 1
        """,
        (int(cobranca_id),),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def confirmar_pagamento_portal(cobranca_id, payment_method=""):
    cobranca = obter_checkout_portal(cobranca_id)
    if not cobranca:
        raise ValueError("Checkout nao encontrado.")

    agora = datetime.now()
    pago_em = agora.isoformat(timespec="seconds")
    proximo_vencimento = (agora + timedelta(days=30)).isoformat(timespec="seconds")

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE portal_cobrancas
        SET
            status = 'pago',
            payment_method = ?,
            paid_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            str(payment_method or cobranca.get("payment_method") or "").strip().lower(),
            pago_em,
            pago_em,
            int(cobranca_id),
        ),
    )
    cursor.execute(
        """
        UPDATE portal_assinaturas
        SET
            status = 'active',
            started_at = COALESCE(NULLIF(started_at, ''), ?),
            next_due_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            pago_em,
            proximo_vencimento,
            pago_em,
            int(cobranca["assinatura_id"]),
        ),
    )
    conn.commit()
    conn.close()


def atualizar_checkout_portal_status(
    cobranca_id,
    status,
    payment_method="",
    external_ref="",
):
    cobranca = obter_checkout_portal(cobranca_id)
    if not cobranca:
        raise ValueError("Checkout nao encontrado.")

    status_normalizado = str(status or "").strip().lower()
    if status_normalizado not in {"pendente", "falhou", "cancelado"}:
        raise ValueError("Status de checkout invalido.")

    agora = _utc_now_iso()
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE portal_cobrancas
        SET
            status = ?,
            payment_method = ?,
            external_ref = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            status_normalizado,
            str(payment_method or cobranca.get("payment_method") or "").strip().lower(),
            str(external_ref or "").strip(),
            agora,
            int(cobranca_id),
        ),
    )
    cursor.execute(
        """
        UPDATE portal_assinaturas
        SET
            status = CASE
                WHEN ? = 'pendente' THEN 'checkout'
                WHEN ? = 'falhou' THEN 'checkout'
                WHEN ? = 'cancelado' THEN 'cancelled'
                ELSE status
            END,
            updated_at = ?
        WHERE id = ?
        """,
        (
            status_normalizado,
            status_normalizado,
            status_normalizado,
            agora,
            int(cobranca["assinatura_id"]),
        ),
    )
    conn.commit()
    conn.close()


def listar_assinaturas_portal_cliente(cliente_id):
    conn = _connect()
    conn.row_factory = _dict_factory
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            a.*,
            p.nome AS plano_nome,
            p.valor_mensal,
            p.recursos_json
        FROM portal_assinaturas a
        JOIN planos_cobranca p ON p.code = a.plano_code
        WHERE a.cliente_id = ?
        ORDER BY a.updated_at DESC, a.id DESC
        """,
        (int(cliente_id),),
    )
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        try:
            row["recursos"] = json.loads(row.get("recursos_json") or "[]")
        except Exception:
            row["recursos"] = []
    return rows


def obter_assinatura_portal_ativa(cliente_id, incluir_checkout=False):
    assinaturas = listar_assinaturas_portal_cliente(cliente_id)
    status_validos = {"active", "paid"}
    if incluir_checkout:
        status_validos.add("checkout")

    for assinatura in assinaturas:
        if str(assinatura.get("status") or "").lower() in status_validos:
            return assinatura
    return assinaturas[0] if assinaturas else None


def listar_cobrancas_portal_cliente(cliente_id, limit=24):
    conn = _connect()
    conn.row_factory = _dict_factory
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            c.*,
            p.nome AS plano_nome
        FROM portal_cobrancas c
        JOIN planos_cobranca p ON p.code = c.plano_code
        WHERE c.cliente_id = ?
        ORDER BY c.created_at DESC, c.id DESC
        LIMIT ?
        """,
        (int(cliente_id), int(limit)),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def listar_assinaturas_portal(limit=200):
    conn = _connect()
    conn.row_factory = _dict_factory
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            a.*,
            p.nome AS plano_nome,
            p.valor_mensal,
            pc.nome AS cliente_nome,
            pc.email AS cliente_email
        FROM portal_assinaturas a
        JOIN planos_cobranca p ON p.code = a.plano_code
        JOIN portal_clientes pc ON pc.id = a.cliente_id
        ORDER BY a.updated_at DESC, a.id DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def obter_metricas_portal():
    assinaturas = listar_assinaturas_portal(limit=1000)
    agora = datetime.now()

    total_clientes = len({assinatura["cliente_id"] for assinatura in assinaturas})
    total_ativas = 0
    total_atrasadas = 0
    total_canceladas = 0

    for assinatura in assinaturas:
        status = str(assinatura.get("status") or "").lower()
        next_due_at = _parse_iso_datetime(assinatura.get("next_due_at"))

        if status in {"cancelled", "blocked", "suspended"}:
            total_canceladas += 1
            continue

        if next_due_at and next_due_at < agora and status not in {"checkout"}:
            total_atrasadas += 1
            continue

        if status in {"active", "paid", "checkout"}:
            total_ativas += 1

    return {
        "clientes": total_clientes,
        "ativas": total_ativas,
        "atrasadas": total_atrasadas,
        "canceladas": total_canceladas,
    }


def avaliar_status_cobranca():
    assinatura = obter_assinatura_sistema()
    if not assinatura:
        return {
            "ok": True,
            "reason": "billing_not_configured",
            "assinatura": None,
        }

    status = str(assinatura.get("status") or "development").strip().lower()
    agora = datetime.now()
    next_due_at = _parse_iso_datetime(assinatura.get("next_due_at"))
    grace_until = _parse_iso_datetime(assinatura.get("grace_until"))

    if status in BILLING_BLOCKED_STATUSES:
        return {
            "ok": False,
            "reason": "billing_blocked",
            "assinatura": assinatura,
        }

    if status not in BILLING_ACTIVE_STATUSES:
        return {
            "ok": True,
            "reason": "billing_unknown",
            "assinatura": assinatura,
        }

    if next_due_at and next_due_at < agora:
        if grace_until and grace_until >= agora:
            assinatura["billing_warning"] = True
            return {
                "ok": True,
                "reason": "billing_grace_period",
                "assinatura": assinatura,
            }

        return {
            "ok": False,
            "reason": "billing_overdue",
            "assinatura": assinatura,
        }

    return {
        "ok": True,
        "reason": "billing_active",
        "assinatura": assinatura,
    }


def criar_usuario(nome, username, password, role="operador"):
    nome = (nome or "").strip()
    username = _normalizar_email(username)
    password = password or ""
    role = (role or "operador").strip().lower()

    if not nome or not username or not password:
        raise ValueError("Nome, usuario e senha sao obrigatorios.")

    _validar_email(username)

    if len(password) < 4:
        raise ValueError("A senha precisa ter pelo menos 4 caracteres.")

    salt_hex, hash_hex = _hash_password(password)
    agora = datetime.now().isoformat(timespec="seconds")
    total_usuarios = contar_usuarios()
    primeiro_usuario = total_usuarios == 0
    approval_status = "approved" if primeiro_usuario else "pending"
    aprovado_em = agora if primeiro_usuario else None

    if primeiro_usuario and role != "admin":
        role = "admin"

    conn = _connect()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO usuarios (
                nome,
                username,
                password_salt,
                password_hash,
                role,
                ativo,
                approval_status,
                approved_at,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nome,
                username,
                salt_hex,
                hash_hex,
                role,
                1 if primeiro_usuario else 0,
                approval_status,
                aprovado_em,
                agora,
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError("Ja existe um usuario com esse login.") from exc
    finally:
        conn.commit()
        conn.close()

    return {
        "primeiro_usuario": primeiro_usuario,
        "approval_status": approval_status,
        "role": role,
    }


def autenticar_usuario(username, password):
    username = _normalizar_email(username)
    password = password or ""

    billing_status = avaliar_status_cobranca()
    if not billing_status.get("ok"):
        return {
            "ok": False,
            "reason": billing_status.get("reason", "billing_blocked"),
            "assinatura": billing_status.get("assinatura"),
        }

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            nome,
            username,
            password_salt,
            password_hash,
            role,
            ativo,
            approval_status
        FROM usuarios
        WHERE username = ?
        LIMIT 1
        """,
        (username,),
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"ok": False, "reason": "invalid_credentials"}

    (
        user_id,
        nome,
        login,
        salt_hex,
        hash_hex,
        role,
        ativo,
        approval_status,
    ) = row

    if not _verificar_password(password, salt_hex, hash_hex):
        conn.close()
        return {"ok": False, "reason": "invalid_credentials"}

    if approval_status != "approved":
        conn.close()
        return {"ok": False, "reason": "pending_approval"}

    if not ativo:
        conn.close()
        return {"ok": False, "reason": "inactive_user"}

    agora = datetime.now().isoformat(timespec="seconds")
    cursor.execute(
        "UPDATE usuarios SET last_login_at = ? WHERE id = ?",
        (agora, user_id),
    )
    conn.commit()
    conn.close()

    return {
        "ok": True,
        "usuario": {
            "id": user_id,
            "nome": nome,
            "username": login,
            "role": role,
            "last_login_at": agora,
        },
        "assinatura": billing_status.get("assinatura"),
        "billing_reason": billing_status.get("reason"),
    }


def listar_usuarios_pendentes():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            nome,
            username,
            role,
            created_at
        FROM usuarios
        WHERE approval_status = 'pending'
        ORDER BY created_at ASC
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "nome": row[1],
            "username": row[2],
            "role": row[3],
            "created_at": row[4],
        }
        for row in rows
    ]


def aprovar_usuario(user_id, admin_user):
    if not admin_user or admin_user.get("role") != "admin":
        raise ValueError("Apenas admins podem aprovar acessos.")

    agora = datetime.now().isoformat(timespec="seconds")
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE usuarios
        SET
            ativo = 1,
            approval_status = 'approved',
            approved_by = ?,
            approved_at = ?
        WHERE id = ?
        """,
        (admin_user.get("id"), agora, user_id),
    )
    conn.commit()
    conn.close()


def registrar_emissao_auditoria(
    usuario,
    item,
    status,
    numero_nfse="",
    caminho_planilha="",
    municipio="",
    ano="",
    mes="",
    excel_row=None,
    mensagem="",
):
    conn = _connect()
    cursor = conn.cursor()
    agora = datetime.now().isoformat(timespec="seconds")
    cursor.execute(
        """
        INSERT INTO emissoes_auditoria (
            usuario_id,
            usuario_nome,
            role,
            item,
            status,
            numero_nfse,
            caminho_planilha,
            municipio,
            ano,
            mes,
            excel_row,
            mensagem,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            usuario.get("id") if usuario else None,
            usuario.get("nome") if usuario else "Sistema",
            usuario.get("role") if usuario else "sistema",
            item,
            status,
            numero_nfse,
            caminho_planilha,
            municipio,
            ano,
            mes,
            excel_row,
            mensagem,
            agora,
        ),
    )
    conn.commit()
    conn.close()


def salvar_nota_importada(dados_nota, usuario):
    agora = datetime.now().isoformat(timespec="seconds")
    conn = _connect()
    cursor = conn.cursor()
    payload_json = json.dumps(dados_nota, ensure_ascii=True)

    cursor.execute(
        """
        INSERT INTO notas_importadas (
            source_type,
            source_file,
            source_ref,
            cliente_nome,
            cliente_documento,
            cliente_email,
            descricao,
            valor_servico,
            ir,
            iss,
            municipio,
            ctn,
            nbs,
            competencia_ano,
            competencia_mes,
            recorrente_key,
            recorrente_score,
            status,
            payload_json,
            imported_by,
            imported_by_name,
            imported_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_type, source_file, COALESCE(source_ref, ''))
        DO UPDATE SET
            cliente_nome=excluded.cliente_nome,
            cliente_documento=excluded.cliente_documento,
            cliente_email=excluded.cliente_email,
            descricao=excluded.descricao,
            valor_servico=excluded.valor_servico,
            ir=excluded.ir,
            iss=excluded.iss,
            municipio=excluded.municipio,
            ctn=excluded.ctn,
            nbs=excluded.nbs,
            competencia_ano=excluded.competencia_ano,
            competencia_mes=excluded.competencia_mes,
            recorrente_key=excluded.recorrente_key,
            recorrente_score=excluded.recorrente_score,
            payload_json=excluded.payload_json,
            imported_by=excluded.imported_by,
            imported_by_name=excluded.imported_by_name,
            updated_at=excluded.updated_at
        """
        if False
        else """
        INSERT OR REPLACE INTO notas_importadas (
            id,
            source_type,
            source_file,
            source_ref,
            cliente_nome,
            cliente_documento,
            cliente_email,
            descricao,
            valor_servico,
            ir,
            iss,
            municipio,
            ctn,
            nbs,
            competencia_ano,
            competencia_mes,
            recorrente_key,
            recorrente_score,
            status,
            payload_json,
            imported_by,
            imported_by_name,
            imported_at,
            updated_at
        )
        VALUES (
            (
                SELECT id
                FROM notas_importadas
                WHERE source_type = ? AND source_file = ? AND source_ref = ?
            ),
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            dados_nota.get("source_type", ""),
            dados_nota.get("source_file", ""),
            dados_nota.get("source_ref", ""),
            dados_nota.get("source_type", ""),
            dados_nota.get("source_file", ""),
            dados_nota.get("source_ref", ""),
            dados_nota.get("cliente_nome", ""),
            dados_nota.get("cliente_documento", ""),
            dados_nota.get("cliente_email", ""),
            dados_nota.get("descricao", ""),
            float(dados_nota.get("valor_servico", 0) or 0),
            float(dados_nota.get("ir", 0) or 0),
            float(dados_nota.get("iss", 0) or 0),
            dados_nota.get("municipio", ""),
            dados_nota.get("ctn", ""),
            dados_nota.get("nbs", ""),
            dados_nota.get("competencia_ano", ""),
            dados_nota.get("competencia_mes", ""),
            dados_nota.get("recorrente_key", ""),
            int(dados_nota.get("recorrente_score", 0) or 0),
            dados_nota.get("status", "IMPORTADA"),
            payload_json,
            usuario.get("id") if usuario else None,
            usuario.get("nome") if usuario else "Sistema",
            dados_nota.get("imported_at", agora),
            agora,
        ),
    )

    nota_id = cursor.lastrowid
    if not nota_id:
        cursor.execute(
            """
            SELECT id FROM notas_importadas
            WHERE source_type = ? AND source_file = ? AND source_ref = ?
            LIMIT 1
            """,
            (
                dados_nota.get("source_type", ""),
                dados_nota.get("source_file", ""),
                dados_nota.get("source_ref", ""),
            ),
        )
        row = cursor.fetchone()
        nota_id = row[0] if row else None

    conn.commit()
    conn.close()
    return nota_id


def _normalizar_nota_importada(nota):
    if not nota:
        return nota

    payload = {}
    if nota.get("payload_json"):
        try:
            payload = json.loads(nota["payload_json"])
        except Exception:
            payload = {}

    if not (nota.get("cliente_nome") or "").strip():
        nota["cliente_nome"] = (
            payload.get("cliente_nome")
            or payload.get("cliente")
            or payload.get("secretaria")
            or ""
        )

    nota["status_exibicao"] = (
        payload.get("status_origem")
        or payload.get("status_planilha")
        or nota.get("status")
        or ""
    )

    nota["payload"] = payload
    return nota


def listar_notas_importadas(limit=100):
    conn = _connect()
    conn.row_factory = _dict_factory
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            source_type,
            source_file,
            cliente_nome,
            cliente_documento,
            cliente_email,
            descricao,
            valor_servico,
            municipio,
            competencia_ano,
            competencia_mes,
            recorrente_score,
            status,
            payload_json,
            imported_by_name,
            imported_at
        FROM notas_importadas
        ORDER BY imported_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [_normalizar_nota_importada(row) for row in rows]


def obter_nota_importada(nota_id):
    conn = _connect()
    conn.row_factory = _dict_factory
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM notas_importadas
        WHERE id = ?
        LIMIT 1
        """,
        (nota_id,),
    )
    nota = cursor.fetchone()
    conn.close()

    return _normalizar_nota_importada(nota)


def contar_notas_importadas():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM notas_importadas")
    total = cursor.fetchone()[0]
    conn.close()
    return total


def excluir_notas_importadas_sem_cliente():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM notas_importadas
        WHERE cliente_nome IS NULL OR TRIM(cliente_nome) = ''
        """
    )
    total = cursor.rowcount
    conn.commit()
    conn.close()
    return total


def excluir_todas_notas_importadas():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notas_importadas")
    total_notas = cursor.rowcount
    cursor.execute("DELETE FROM modelos_recorrentes")
    total_modelos = cursor.rowcount
    conn.commit()
    conn.close()
    return {"notas": total_notas, "modelos": total_modelos}


def criar_modelo_recorrente_de_nota(nota_id, usuario, nome_modelo=None, periodicidade="mensal"):
    conn = _connect()
    conn.row_factory = _dict_factory
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM notas_importadas WHERE id = ? LIMIT 1",
        (nota_id,),
    )
    nota = cursor.fetchone()

    if not nota:
        conn.close()
        raise ValueError("Nota importada nao encontrada.")

    agora = datetime.now().isoformat(timespec="seconds")
    nome_modelo = (
        nome_modelo
        or f"{nota.get('cliente_nome') or 'Cliente'} - {nota.get('municipio') or 'Modelo'}"
    )

    cursor.execute(
        """
        INSERT INTO modelos_recorrentes (
            nome_modelo,
            cliente_nome,
            cliente_documento,
            cliente_email,
            descricao,
            valor_servico,
            ir,
            iss,
            municipio,
            ctn,
            nbs,
            periodicidade,
            ativo,
            origem_nota_id,
            recorrente_key,
            criado_por,
            criado_por_nome,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            nome_modelo,
            nota.get("cliente_nome", ""),
            nota.get("cliente_documento", ""),
            nota.get("cliente_email", ""),
            nota.get("descricao", ""),
            nota.get("valor_servico", 0),
            nota.get("ir", 0),
            nota.get("iss", 0),
            nota.get("municipio", ""),
            nota.get("ctn", ""),
            nota.get("nbs", ""),
            periodicidade,
            1,
            nota_id,
            nota.get("recorrente_key", ""),
            usuario.get("id") if usuario else None,
            usuario.get("nome") if usuario else "Sistema",
            agora,
            agora,
        ),
    )

    modelo_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return modelo_id


def listar_modelos_recorrentes(limit=50):
    conn = _connect()
    conn.row_factory = _dict_factory
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            nome_modelo,
            cliente_nome,
            cliente_documento,
            cliente_email,
            descricao,
            valor_servico,
            municipio,
            periodicidade,
            recorrente_key,
            criado_por_nome,
            created_at
        FROM modelos_recorrentes
        WHERE ativo = 1
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows
