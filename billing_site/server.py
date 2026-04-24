import json
import os
import secrets
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from database.db import (
    atualizar_status_cobranca,
    atualizar_checkout_portal_status,
    autenticar_cliente_portal,
    avaliar_status_cobranca,
    confirmar_pagamento_portal,
    criar_banco,
    criar_cliente_portal,
    gerar_cobranca_mensal_atual,
    iniciar_checkout_portal,
    listar_assinaturas_portal,
    listar_cobrancas_mensais,
    listar_cobrancas_portal_cliente,
    listar_planos_cobranca,
    obter_assinatura_portal_ativa,
    obter_assinatura_sistema,
    obter_checkout_portal,
    obter_cliente_portal,
    obter_metricas_portal,
    salvar_assinatura_sistema,
)


HOST = os.environ.get("BILLING_SITE_HOST", "127.0.0.1")
PORT = int(os.environ.get("BILLING_SITE_PORT", "8765"))
SESSIONS = {}
PLAN_CONTENT = {
    "emissor": {
        "headline": "Emita suas notas com mais velocidade e menos retrabalho.",
        "pitch": "Ideal para quem quer organizar a operação fiscal e padronizar a emissão sem depender de processos manuais.",
        "gains": [
            "Emissão centralizada da NFS-e",
            "Fluxo operacional guiado no desktop",
            "Mais controle sobre itens, município e filtros",
        ],
    },
    "emissor_email": {
        "headline": "Além de emitir, entregue a nota por email automaticamente.",
        "pitch": "Perfeito para reduzir o trabalho administrativo depois da emissão e acelerar a entrega ao cliente.",
        "gains": [
            "Tudo do plano Emissor",
            "Disparo de email com anexos PDF e XML",
            "Mais agilidade no pós-emissão",
        ],
    },
    "emissor_email_whatsapp": {
        "headline": "Automação premium para emissão e entrega multicanal.",
        "pitch": "Plano mais completo para quem quer ganhar velocidade comercial, fiscal e operacional no mesmo fluxo.",
        "gains": [
            "Tudo do plano Emissor + Email",
            "Envio automático por WhatsApp",
            "Experiência mais rápida para o cliente final",
        ],
    },
}


def _fmt_money(valor):
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0.0
    return f"R$ {numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_dt_local(valor):
    texto = str(valor or "").strip()
    return texto[:16] if texto else ""


def _plan_badge(status):
    mapa = {
        "development": ("Desenvolvimento", "info"),
        "active": ("Ativa", "success"),
        "paid": ("Paga", "success"),
        "trial": ("Avaliação", "info"),
        "blocked": ("Bloqueada", "danger"),
        "suspended": ("Suspensa", "warning"),
        "cancelled": ("Cancelada", "danger"),
        "checkout": ("Checkout", "warning"),
    }
    return mapa.get(str(status or "").lower(), (str(status or "Desconhecido"), "info"))


def _charge_badge(status):
    mapa = {
        "pendente": ("Pendente", "warning"),
        "pago": ("Pago", "success"),
        "cancelado": ("Cancelado", "danger"),
        "falhou": ("Falhou", "danger"),
    }
    return mapa.get(str(status or "").lower(), (str(status or "Pendente"), "info"))


def _layout(conteudo, titulo="MBS Fiscal SaaS", mensagem="", erro=""):
    flash = ""
    if mensagem:
        flash = f'<div class="flash flash-ok">{escape(mensagem)}</div>'
    elif erro:
        flash = f'<div class="flash flash-error">{escape(erro)}</div>'

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(titulo)}</title>
  <style>
    :root {{
      --bg: #07101d;
      --panel: #0e1a2f;
      --panel-soft: #142542;
      --line: #27476f;
      --text: #eef5ff;
      --muted: #94a8cb;
      --blue: #4390ff;
      --green: #35d697;
      --amber: #f6bd56;
      --red: #ff6f88;
      --shadow: 0 28px 80px rgba(0, 0, 0, .34);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Trebuchet MS", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(67,144,255,.20), transparent 26%),
        radial-gradient(circle at bottom right, rgba(53,214,151,.10), transparent 22%),
        var(--bg);
    }}
    a {{ color: inherit; text-decoration: none; }}
    .shell {{
      width: min(1200px, calc(100vw - 44px));
      margin: 22px auto 40px;
    }}
    .nav {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 18px;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 800;
      letter-spacing: .04em;
    }}
    .brand-badge {{
      width: 38px;
      height: 38px;
      border-radius: 12px;
      background: linear-gradient(135deg, var(--blue), #2558c8);
      display: grid;
      place-items: center;
      box-shadow: var(--shadow);
    }}
    .nav-links {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .nav-links a {{
      background: rgba(255,255,255,.03);
      border: 1px solid rgba(255,255,255,.06);
      padding: 10px 14px;
      border-radius: 999px;
      color: var(--muted);
      font-size: 14px;
    }}
    .nav-links a.primary {{
      background: rgba(67,144,255,.16);
      color: var(--text);
      border-color: rgba(67,144,255,.22);
    }}
    .hero {{
      background: linear-gradient(135deg, rgba(20,37,66,.96), rgba(10,18,33,.96));
      border: 1px solid rgba(67,144,255,.18);
      border-radius: 30px;
      padding: 30px;
      box-shadow: var(--shadow);
      display: grid;
      grid-template-columns: 1.4fr .9fr;
      gap: 22px;
    }}
    .eyebrow {{
      color: var(--blue);
      text-transform: uppercase;
      letter-spacing: .18em;
      font-size: 12px;
      margin-bottom: 14px;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 44px;
      line-height: 1.04;
    }}
    .hero p {{
      margin: 0;
      color: var(--muted);
      font-size: 16px;
      line-height: 1.7;
      max-width: 720px;
    }}
    .hero-side {{
      display: grid;
      gap: 12px;
      align-content: start;
    }}
    .meta-card, .card {{
      background: linear-gradient(180deg, rgba(15,27,49,.98), rgba(10,18,32,.98));
      border: 1px solid rgba(67,144,255,.14);
      border-radius: 24px;
      box-shadow: var(--shadow);
    }}
    .meta-card {{
      padding: 18px;
    }}
    .meta-label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .14em;
      margin-bottom: 6px;
    }}
    .meta-value {{
      font-size: 20px;
      font-weight: 800;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 18px;
      margin-top: 18px;
    }}
    .card {{ padding: 22px; }}
    .span-3 {{ grid-column: span 3; }}
    .span-4 {{ grid-column: span 4; }}
    .span-5 {{ grid-column: span 5; }}
    .span-6 {{ grid-column: span 6; }}
    .span-7 {{ grid-column: span 7; }}
    .span-8 {{ grid-column: span 8; }}
    .span-12 {{ grid-column: span 12; }}
    .section-title {{
      margin: 0 0 16px;
      font-size: 26px;
    }}
    .subtitle {{
      margin: -4px 0 18px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.6;
    }}
    .kpi-label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .12em;
    }}
    .kpi-value {{
      margin-top: 10px;
      font-size: 34px;
      font-weight: 800;
    }}
    .plans {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
    }}
    .plan {{
      border: 1px solid rgba(255,255,255,.06);
      border-radius: 22px;
      padding: 20px;
      background: rgba(255,255,255,.02);
      display: grid;
      gap: 12px;
    }}
    .plan.featured {{
      border-color: rgba(67,144,255,.28);
      background: linear-gradient(180deg, rgba(67,144,255,.14), rgba(67,144,255,.04));
    }}
    .plan h3 {{
      margin: 0;
      font-size: 22px;
    }}
    .plan-price {{
      font-size: 34px;
      font-weight: 900;
    }}
    .muted {{ color: var(--muted); }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 8px 12px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: .08em;
      text-transform: uppercase;
    }}
    .badge.success {{ background: rgba(53,214,151,.14); color: var(--green); }}
    .badge.warning {{ background: rgba(246,189,86,.14); color: var(--amber); }}
    .badge.danger {{ background: rgba(255,111,136,.16); color: var(--red); }}
    .badge.info {{ background: rgba(67,144,255,.16); color: var(--blue); }}
    ul {{
      margin: 0;
      padding-left: 18px;
      color: var(--muted);
      line-height: 1.7;
    }}
    form {{
      display: grid;
      gap: 14px;
    }}
    .form-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 14px;
    }}
    label {{
      display: grid;
      gap: 8px;
      font-size: 13px;
      color: var(--muted);
    }}
    input, select, textarea, button {{
      font: inherit;
    }}
    input, select, textarea {{
      width: 100%;
      border-radius: 14px;
      border: 1px solid rgba(67,144,255,.18);
      background: rgba(18,33,59,.96);
      color: var(--text);
      padding: 12px 14px;
      outline: none;
    }}
    textarea {{ min-height: 90px; resize: vertical; }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    button, .button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border: 0;
      border-radius: 14px;
      padding: 12px 16px;
      cursor: pointer;
      font-weight: 800;
    }}
    .btn-primary {{
      background: linear-gradient(135deg, #4390ff, #2c67db);
      color: white;
    }}
    .btn-soft {{
      background: rgba(67,144,255,.10);
      color: var(--text);
      border: 1px solid rgba(67,144,255,.16);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 10px;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      border-bottom: 1px solid rgba(255,255,255,.06);
      padding: 14px 10px;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .12em;
    }}
    .flash {{
      margin: 0 0 18px;
      border-radius: 16px;
      padding: 14px 16px;
      font-size: 14px;
      border: 1px solid transparent;
    }}
    .flash-ok {{
      background: rgba(53,214,151,.14);
      color: var(--green);
      border-color: rgba(53,214,151,.22);
    }}
    .flash-error {{
      background: rgba(255,111,136,.16);
      color: #ffc0cb;
      border-color: rgba(255,111,136,.22);
    }}
    .steps {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 14px;
      margin-top: 18px;
    }}
    .step {{
      border-radius: 18px;
      padding: 16px;
      background: rgba(255,255,255,.02);
      border: 1px solid rgba(255,255,255,.06);
    }}
    .small {{
      font-size: 13px;
      color: var(--muted);
      line-height: 1.6;
    }}
    .checkout-option {{
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 18px;
      padding: 16px;
      background: rgba(255,255,255,.02);
    }}
    .checkout-methods {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 14px;
    }}
    .qr-box {{
      display: grid;
      place-items: center;
      width: 260px;
      height: 260px;
      margin: 8px auto 0;
      border-radius: 24px;
      border: 1px solid rgba(67,144,255,.18);
      background:
        linear-gradient(45deg, rgba(67,144,255,.08) 25%, transparent 25%),
        linear-gradient(-45deg, rgba(67,144,255,.08) 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, rgba(67,144,255,.08) 75%),
        linear-gradient(-45deg, transparent 75%, rgba(67,144,255,.08) 75%);
      background-size: 28px 28px;
      background-position: 0 0, 0 14px, 14px -14px, -14px 0;
      box-shadow: inset 0 0 0 12px rgba(255,255,255,.02);
    }}
    .qr-core {{
      width: 96px;
      height: 96px;
      border-radius: 20px;
      background: linear-gradient(135deg, #4390ff, #1d3f86);
      display: grid;
      place-items: center;
      font-size: 13px;
      font-weight: 900;
      letter-spacing: .16em;
      text-transform: uppercase;
      color: white;
    }}
    .code-box {{
      background: rgba(0,0,0,.18);
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 18px;
      padding: 16px;
      font-family: Consolas, monospace;
      font-size: 13px;
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-all;
    }}
    .status-line {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .api-box {{
      background: rgba(0,0,0,.20);
      border-radius: 18px;
      border: 1px solid rgba(255,255,255,.06);
      padding: 16px;
      font-family: Consolas, monospace;
      font-size: 13px;
      white-space: pre-wrap;
      color: #dbe8ff;
    }}
    @media (max-width: 960px) {{
      .hero, .plans, .steps, .form-grid, .checkout-methods {{
        grid-template-columns: 1fr;
      }}
      .span-3, .span-4, .span-5, .span-6, .span-7, .span-8, .span-12 {{
        grid-column: span 12;
      }}
      .shell {{ width: calc(100vw - 24px); }}
      h1 {{ font-size: 34px; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    {flash}
    {conteudo}
  </div>
</body>
</html>"""


def _cookie_header(name, value, max_age=86400):
    return f"{name}={value}; Path=/; HttpOnly; Max-Age={max_age}; SameSite=Lax"


class BillingHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _read_form(self):
        tamanho = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(tamanho).decode("utf-8") if tamanho else ""
        return {k: v[0] for k, v in parse_qs(raw).items()}

    def _query(self):
        parsed = urlparse(self.path)
        return parsed, parse_qs(parsed.query)

    def _parse_cookies(self):
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        return {chave: morsel.value for chave, morsel in cookie.items()}

    def _cliente_logado(self):
        cookies = self._parse_cookies()
        token = cookies.get("portal_session")
        cliente_id = SESSIONS.get(token)
        if not cliente_id:
            return None
        return obter_cliente_portal(cliente_id)

    def _redirect(self, path, cookie=None, clear_cookie=False):
        self.send_response(303)
        self.send_header("Location", path)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        if clear_cookie:
            self.send_header("Set-Cookie", _cookie_header("portal_session", "", max_age=0))
        self.end_headers()

    def _json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _html(self, html):
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _render_nav(self, cliente=None):
        cliente_links = (
            f'<a href="/portal" class="primary">Área do usuário</a>'
            f'<a href="/logout">Sair</a>'
        ) if cliente else (
            '<a href="/login">Entrar</a>'
            '<a href="/cadastro" class="primary">Criar conta</a>'
        )
        return f"""
        <div class="nav">
          <div class="brand">
            <div class="brand-badge">M</div>
            <div>
              <div style="font-size:18px;">MBS Fiscal</div>
              <div class="small">Planos, cobrança e portal do cliente</div>
            </div>
          </div>
          <div class="nav-links">
            <a href="/">Planos</a>
            <a href="/admin">Admin</a>
            {cliente_links}
          </div>
        </div>
        """

    def _render_home(self, mensagem="", erro=""):
        cliente = self._cliente_logado()
        planos = listar_planos_cobranca(apenas_ativos=True)

        plan_cards = []
        for idx, plano in enumerate(planos):
            conteudo_plano = PLAN_CONTENT.get(plano.get("code"), {})
            recursos = "".join(
                f"<li>{escape(str(recurso).replace('_', ' ').title())}</li>"
                for recurso in plano.get("recursos", [])
            )
            ganhos = "".join(
                f"<li>{escape(item)}</li>"
                for item in conteudo_plano.get("gains", [])
            )
            featured = "featured" if idx == len(planos) - 1 else ""
            plan_cards.append(
                f"""
                <article class="plan {featured}">
                  <div class="badge info">{escape(plano.get('code', ''))}</div>
                  <h3>{escape(plano.get('nome', 'Plano'))}</h3>
                  <div class="plan-price">{escape(_fmt_money(plano.get('valor_mensal', 0)))}</div>
                  <div class="small"><strong>{escape(conteudo_plano.get('headline', 'Plano pronto para operação fiscal.'))}</strong></div>
                  <div class="small">{escape(conteudo_plano.get('pitch', 'Ciclo mensal com liberação dos recursos do sistema conforme o plano contratado.'))}</div>
                  <div class="small">O que o cliente ganha:</div>
                  <ul>{ganhos or recursos}</ul>
                  <a class="button btn-primary" href="/contratar?plan={escape(plano.get('code', ''))}">Escolher plano</a>
                </article>
                """
            )

        conteudo = f"""
        {self._render_nav(cliente)}
        <section class="hero">
          <div>
            <div class="eyebrow">Portal Comercial</div>
            <h1>Escolha o plano ideal, conclua a contratação e acompanhe sua assinatura</h1>
            <p>Este portal reúne a vitrine dos planos, autenticação do cliente, contratação, checkout e área do usuário com assinatura ativa, histórico financeiro e recursos liberados.</p>
            <div class="steps">
              <div class="step"><strong>1. Escolha o plano</strong><div class="small">O cliente começa pela página inicial e seleciona a oferta ideal.</div></div>
              <div class="step"><strong>2. Entre ou cadastre-se</strong><div class="small">Se já tiver conta, faz login. Se não, cria a conta com os dados do portal.</div></div>
              <div class="step"><strong>3. Checkout</strong><div class="small">Depois do cadastro, escolhe PIX ou cartão e entra na área do usuário.</div></div>
            </div>
          </div>
          <div class="hero-side">
            <div class="meta-card">
              <div class="meta-label">Operação</div>
              <div class="meta-value">Portal online</div>
            </div>
            <div class="meta-card">
              <div class="meta-label">Portal do cliente</div>
              <div class="meta-value">{escape(cliente.get('nome')) if cliente else 'Não autenticado'}</div>
            </div>
            <div class="meta-card">
              <div class="meta-label">Próximo passo</div>
              <div class="meta-value">{'Ir para checkout' if cliente else 'Escolher plano'}</div>
            </div>
          </div>
        </section>
        <section class="grid">
          <article class="card span-12">
            <h2 class="section-title">Planos disponíveis</h2>
            <p class="subtitle">Cada plano foi apresentado para conduzir o cliente da escolha até a ativação, com posicionamento comercial claro e foco em conversão.</p>
            <div class="plans">
              {''.join(plan_cards)}
            </div>
          </article>
        </section>
        """
        return _layout(conteudo, mensagem=mensagem, erro=erro)

    def _render_auth_page(self, modo="login", plano_code="", erro=""):
        cliente = self._cliente_logado()
        planos = {plano["code"]: plano for plano in listar_planos_cobranca(apenas_ativos=True)}
        plano = planos.get(plano_code) if plano_code else None
        titulo = "Entrar na conta" if modo == "login" else "Criar conta"
        subtitulo = (
            "Entre com seu email para continuar a contratação do plano."
            if modo == "login"
            else "Cadastre os dados do cliente para seguir para o checkout."
        )
        plano_box = ""
        if plano:
            plano_box = f"""
            <div class="checkout-option">
              <div class="badge info">Plano selecionado</div>
              <h3 style="margin:10px 0 6px;">{escape(plano.get('nome', 'Plano'))}</h3>
              <div class="small">{escape(_fmt_money(plano.get('valor_mensal', 0)))} por mês</div>
            </div>
            """

        if modo == "login":
            form = f"""
            <form method="post" action="/auth/login">
              <input type="hidden" name="plan" value="{escape(plano_code)}">
              <label>Email
                <input type="email" name="email" required>
              </label>
              <label>Senha
                <input type="password" name="password" required>
              </label>
              <div class="actions">
                <button class="btn-primary" type="submit">Entrar e continuar</button>
                <a class="button btn-soft" href="/cadastro?plan={escape(plano_code)}">Ainda não tenho conta</a>
              </div>
            </form>
            """
        else:
            form = f"""
            <form method="post" action="/auth/register">
              <input type="hidden" name="plan" value="{escape(plano_code)}">
              <div class="form-grid">
                <label>Nome completo
                  <input type="text" name="nome" required>
                </label>
                <label>Email
                  <input type="email" name="email" required>
                </label>
                <label>Telefone
                  <input type="text" name="telefone">
                </label>
                <label>Documento
                  <input type="text" name="documento">
                </label>
              </div>
              <label>Endereço
                <textarea name="endereco"></textarea>
              </label>
              <div class="form-grid">
                <label>Senha
                  <input type="password" name="password" required>
                </label>
                <label>Confirme a senha
                  <input type="password" name="password_confirm" required>
                </label>
              </div>
              <div class="actions">
                <button class="btn-primary" type="submit">Criar conta e continuar</button>
                <a class="button btn-soft" href="/login?plan={escape(plano_code)}">Já tenho conta</a>
              </div>
            </form>
            """

        conteudo = f"""
        {self._render_nav(cliente)}
        <section class="grid">
          <article class="card span-7">
            <h1 style="font-size:34px;margin-bottom:10px;">{escape(titulo)}</h1>
            <p class="subtitle">{escape(subtitulo)}</p>
            {form}
          </article>
          <article class="card span-5">
            <h2 class="section-title">Fluxo da contratação</h2>
            <div class="small">Escolha do plano → login ou cadastro → checkout → área do usuário.</div>
            <div style="margin-top:14px;">{plano_box}</div>
          </article>
        </section>
        """
        return _layout(conteudo, titulo=titulo, erro=erro)

    def _render_choose_plan(self, plano_code="", mensagem="", erro=""):
        cliente = self._cliente_logado()
        planos = {plano["code"]: plano for plano in listar_planos_cobranca(apenas_ativos=True)}
        plano = planos.get(plano_code)
        if not plano:
            return self._render_home(erro="Plano não encontrado.")
        conteudo_plano = PLAN_CONTENT.get(plano_code, {})

        if cliente:
            return self._redirect(f"/checkout?plan={plano_code}")

        conteudo = f"""
        {self._render_nav(cliente)}
        <section class="grid">
          <article class="card span-7">
            <div class="badge info">Plano escolhido</div>
            <h1 style="font-size:34px;margin:12px 0 10px;">{escape(plano.get('nome', 'Plano'))}</h1>
            <p class="subtitle">Antes de seguir para o pagamento, o cliente pode entrar com a conta existente ou concluir um novo cadastro em poucos passos.</p>
            <div class="actions">
              <a class="button btn-primary" href="/login?plan={escape(plano_code)}">Já tenho login</a>
              <a class="button btn-soft" href="/cadastro?plan={escape(plano_code)}">Ainda não tenho conta</a>
            </div>
          </article>
          <article class="card span-5">
            <h2 class="section-title">Resumo da oferta</h2>
            <div class="plan featured">
              <h3>{escape(plano.get('nome', 'Plano'))}</h3>
              <div class="plan-price">{escape(_fmt_money(plano.get('valor_mensal', 0)))}</div>
              <div class="small"><strong>{escape(conteudo_plano.get('headline', ''))}</strong></div>
              <div class="small">{escape(conteudo_plano.get('pitch', ''))}</div>
              <ul>{''.join(f"<li>{escape(item)}</li>" for item in conteudo_plano.get('gains', [])) or ''.join(f"<li>{escape(str(recurso).replace('_', ' ').title())}</li>" for recurso in plano.get('recursos', []))}</ul>
            </div>
          </article>
        </section>
        """
        return _layout(conteudo, mensagem=mensagem, erro=erro)

    def _render_checkout(self, cliente, plano_code="", erro=""):
        if not cliente:
            return self._redirect("/login")

        planos = {plano["code"]: plano for plano in listar_planos_cobranca(apenas_ativos=True)}
        plano = planos.get(plano_code)
        if not plano:
            return self._render_home(erro="Plano não encontrado para checkout.")

        conteudo = f"""
        {self._render_nav(cliente)}
        <section class="grid">
          <article class="card span-7">
            <h1 style="font-size:34px;margin-bottom:10px;">Checkout do plano</h1>
            <p class="subtitle">Escolha a forma de pagamento e siga para a etapa correspondente. O fluxo já está organizado para PIX e cartão em jornadas separadas.</p>
            <form method="post" action="/checkout/iniciar">
              <input type="hidden" name="plan" value="{escape(plano_code)}">
              <div class="checkout-methods">
                <div class="checkout-option">
                  <label><input type="radio" name="payment_method" value="pix" checked> PIX</label>
                  <div class="small">Exibe QR Code, código copia e cola e status da cobrança para acompanhar a confirmação do pagamento.</div>
                </div>
                <div class="checkout-option">
                  <label><input type="radio" name="payment_method" value="cartao"> Cartão</label>
                  <div class="small">Abre o formulário de cartão para concluir a contratação com rapidez e segurança.</div>
                </div>
              </div>
              <div class="actions">
                <button class="btn-primary" type="submit">Continuar para o método escolhido</button>
                <a class="button btn-soft" href="/portal">Voltar para área do usuário</a>
              </div>
            </form>
          </article>
          <article class="card span-5">
            <h2 class="section-title">Resumo da contratação</h2>
            <div class="meta-card">
              <div class="meta-label">Cliente</div>
              <div class="meta-value">{escape(cliente.get('nome', ''))}</div>
            </div>
            <div class="meta-card" style="margin-top:12px;">
              <div class="meta-label">Plano</div>
              <div class="meta-value">{escape(plano.get('nome', 'Plano'))}</div>
            </div>
            <div class="meta-card" style="margin-top:12px;">
              <div class="meta-label">Mensalidade</div>
              <div class="meta-value">{escape(_fmt_money(plano.get('valor_mensal', 0)))}</div>
            </div>
          </article>
        </section>
        """
        return _layout(conteudo, titulo="Checkout", erro=erro)

    def _gerar_pix_sandbox(self, checkout):
        token = checkout.get("checkout_token") or secrets.token_hex(8)
        valor = f"{float(checkout.get('valor', 0) or 0):.2f}"
        return (
            "00020126580014BR.GOV.BCB.PIX0136"
            f"{token}520400005303986540{len(valor):02d}{valor}"
            "5802BR5913MBS FISCAL6009FORTALEZA62070503***6304ABCD"
        )

    def _render_pix_checkout(self, cliente, checkout_id, erro=""):
        if not cliente:
            return self._redirect("/login")

        checkout = obter_checkout_portal(checkout_id)
        if not checkout or int(checkout.get("cliente_id", 0)) != int(cliente["id"]):
            return self._render_portal(cliente, erro="Checkout PIX não encontrado.")

        badge_texto, badge_tipo = _charge_badge(checkout.get("status"))
        pix_code = self._gerar_pix_sandbox(checkout)

        conteudo = f"""
        {self._render_nav(cliente)}
        <section class="grid">
          <article class="card span-7">
            <div class="status-line">
              <div>
                <h1 style="font-size:34px;margin:0 0 10px;">Pagamento via PIX</h1>
                <p class="subtitle">Use o QR Code ou o código copia e cola para concluir a contratação e ativar o seu plano com agilidade.</p>
              </div>
              <span class="badge {badge_tipo}">{escape(badge_texto)}</span>
            </div>
            <div class="qr-box">
              <div class="qr-core">PIX</div>
            </div>
            <p class="small" style="margin-top:16px;">Apresente este QR Code no aplicativo do banco ou utilize o código copia e cola para concluir o pagamento.</p>
            <div class="code-box">{escape(pix_code)}</div>
            <div class="actions">
              <form method="post" action="/checkout/pix/aprovar">
                <input type="hidden" name="checkout_id" value="{int(checkout.get('id', 0))}">
                <button class="btn-primary" type="submit">Confirmar pagamento</button>
              </form>
              <form method="post" action="/checkout/cancelar">
                <input type="hidden" name="checkout_id" value="{int(checkout.get('id', 0))}">
                <button class="btn-soft" type="submit">Cancelar checkout</button>
              </form>
            </div>
          </article>
          <article class="card span-5">
            <h2 class="section-title">Resumo do pedido</h2>
            <div class="meta-card">
              <div class="meta-label">Plano</div>
              <div class="meta-value">{escape(checkout.get('plano_nome') or '')}</div>
            </div>
            <div class="meta-card" style="margin-top:12px;">
              <div class="meta-label">Valor</div>
              <div class="meta-value">{escape(_fmt_money(checkout.get('valor', 0)))}</div>
            </div>
            <div class="meta-card" style="margin-top:12px;">
              <div class="meta-label">Vencimento</div>
              <div class="meta-value">{escape(checkout.get('due_at') or '-')}</div>
            </div>
          </article>
        </section>
        """
        return _layout(conteudo, titulo="Pagamento via PIX", erro=erro)

    def _render_card_checkout(self, cliente, checkout_id, erro=""):
        if not cliente:
            return self._redirect("/login")

        checkout = obter_checkout_portal(checkout_id)
        if not checkout or int(checkout.get("cliente_id", 0)) != int(cliente["id"]):
            return self._render_portal(cliente, erro="Checkout de cartão não encontrado.")

        badge_texto, badge_tipo = _charge_badge(checkout.get("status"))
        conteudo = f"""
        {self._render_nav(cliente)}
        <section class="grid">
          <article class="card span-7">
            <div class="status-line">
              <div>
                <h1 style="font-size:34px;margin:0 0 10px;">Pagamento por cartão</h1>
                <p class="subtitle">Preencha os dados do cartão para concluir a contratação e liberar o acesso ao plano selecionado.</p>
              </div>
              <span class="badge {badge_tipo}">{escape(badge_texto)}</span>
            </div>
            <form method="post" action="/checkout/cartao/processar">
              <input type="hidden" name="checkout_id" value="{int(checkout.get('id', 0))}">
              <div class="form-grid">
                <label>Nome no cartão
                  <input type="text" name="card_name" value="{escape(cliente.get('nome', ''))}" required>
                </label>
                <label>Número do cartão
                  <input type="text" name="card_number" placeholder="4111 1111 1111 1111" required>
                </label>
                <label>Validade
                  <input type="text" name="card_expiry" placeholder="12/30" required>
                </label>
                <label>CVV
                  <input type="text" name="card_cvv" placeholder="123" required>
                </label>
              </div>
              <div class="small">Após a aprovação, a assinatura é ativada e o histórico financeiro fica disponível na área do usuário.</div>
              <div class="actions">
                <button class="btn-primary" type="submit">Processar pagamento</button>
                <a class="button btn-soft" href="/portal">Voltar para área do usuário</a>
              </div>
            </form>
          </article>
          <article class="card span-5">
            <h2 class="section-title">Resumo do pedido</h2>
            <div class="meta-card">
              <div class="meta-label">Plano</div>
              <div class="meta-value">{escape(checkout.get('plano_nome') or '')}</div>
            </div>
            <div class="meta-card" style="margin-top:12px;">
              <div class="meta-label">Valor</div>
              <div class="meta-value">{escape(_fmt_money(checkout.get('valor', 0)))}</div>
            </div>
            <div class="meta-card" style="margin-top:12px;">
              <div class="meta-label">Forma</div>
              <div class="meta-value">Cartão</div>
            </div>
          </article>
        </section>
        """
        return _layout(conteudo, titulo="Pagamento por cartão", erro=erro)

    def _render_portal(self, cliente, mensagem="", erro=""):
        if not cliente:
            return self._redirect("/login")

        assinatura = obter_assinatura_portal_ativa(cliente["id"], incluir_checkout=True)
        cobrancas = listar_cobrancas_portal_cliente(cliente["id"], limit=24)
        badge_texto, badge_tipo = _plan_badge(assinatura.get("status") if assinatura else "checkout")

        assinatura_box = ""
        if assinatura:
            recursos = "".join(
                f"<li>{escape(str(recurso).replace('_', ' ').title())}</li>"
                for recurso in assinatura.get("recursos", [])
            )
            assinatura_box = f"""
            <div class="plan featured">
              <div class="badge {badge_tipo}">{escape(badge_texto)}</div>
              <h3>{escape(assinatura.get('plano_nome', 'Plano'))}</h3>
              <div class="plan-price">{escape(_fmt_money(assinatura.get('valor_mensal', 0)))}</div>
              <div class="small">Próximo vencimento: {escape(assinatura.get('next_due_at') or 'Ainda não definido')}</div>
              <ul>{recursos}</ul>
            </div>
            """
        else:
            assinatura_box = """
            <div class="checkout-option">
              <div class="small">Você ainda não tem uma assinatura ativa. Escolha um plano para iniciar a contratação.</div>
            </div>
            """

        linhas = []
        for cobranca in cobrancas:
            badge_cobranca_texto, badge_cobranca_tipo = _charge_badge(cobranca.get("status"))
            linhas.append(
                f"""
                <tr>
                  <td>{escape(cobranca.get('plano_nome') or cobranca.get('plano_code') or '')}</td>
                  <td>{escape(f"{int(cobranca.get('referencia_mes', 0)):02d}/{cobranca.get('referencia_ano', '')}")}</td>
                  <td>{escape(_fmt_money(cobranca.get('valor', 0)))}</td>
                  <td><span class="badge {badge_cobranca_tipo}">{escape(badge_cobranca_texto)}</span></td>
                  <td>{escape(cobranca.get('payment_method') or '-')}</td>
                  <td>{escape(cobranca.get('paid_at') or '-')}</td>
                </tr>
                """
            )

        conteudo = f"""
        {self._render_nav(cliente)}
        <section class="grid">
          <article class="card span-4">
            <h2 class="section-title">Área do usuário</h2>
            <div class="small">Cliente autenticado e pronto para contratar, renovar ou consultar o histórico.</div>
            <div style="margin-top:14px;">
              <div class="meta-card">
                <div class="meta-label">Nome</div>
                <div class="meta-value">{escape(cliente.get('nome', ''))}</div>
              </div>
              <div class="meta-card" style="margin-top:12px;">
                <div class="meta-label">Email</div>
                <div class="meta-value">{escape(cliente.get('email', ''))}</div>
              </div>
              <div class="meta-card" style="margin-top:12px;">
                <div class="meta-label">Telefone</div>
                <div class="meta-value">{escape(cliente.get('telefone') or 'Não informado')}</div>
              </div>
            </div>
            <div class="actions" style="margin-top:16px;">
              <a class="button btn-primary" href="/">Contratar outro plano</a>
            </div>
          </article>
          <article class="card span-8">
            <h2 class="section-title">Plano ativo e histórico</h2>
            <p class="subtitle">Depois do pagamento aprovado, o cliente fica nesta área com o plano ativo e o histórico financeiro.</p>
            {assinatura_box}
            <table>
              <thead>
                <tr>
                  <th>Plano</th>
                  <th>Competência</th>
                  <th>Valor</th>
                  <th>Status</th>
                  <th>Pagamento</th>
                  <th>Pago em</th>
                </tr>
              </thead>
              <tbody>
                {''.join(linhas) or '<tr><td colspan="6">Nenhum pagamento encontrado ainda.</td></tr>'}
              </tbody>
            </table>
          </article>
        </section>
        """
        return _layout(conteudo, titulo="Área do usuário", mensagem=mensagem, erro=erro)

    def _render_admin(self, mensagem="", erro=""):
        cliente = self._cliente_logado()
        assinatura = obter_assinatura_sistema() or {}
        cobrancas = listar_cobrancas_mensais(limit=18)
        metricas = obter_metricas_portal()
        assinaturas_portal = listar_assinaturas_portal(limit=40)
        badge_texto, badge_tipo = _plan_badge(assinatura.get("status"))

        linhas = []
        for assinatura_portal in assinaturas_portal:
            badge_assinatura_texto, badge_assinatura_tipo = _plan_badge(assinatura_portal.get("status"))
            linhas.append(
                f"""
                <tr>
                  <td>{escape(assinatura_portal.get('cliente_nome') or '')}<br><span class="muted">{escape(assinatura_portal.get('cliente_email') or '')}</span></td>
                  <td>{escape(assinatura_portal.get('plano_nome') or '')}</td>
                  <td><span class="badge {badge_assinatura_tipo}">{escape(badge_assinatura_texto)}</span></td>
                  <td>{escape(assinatura_portal.get('next_due_at') or '-')}</td>
                </tr>
                """
            )

        conteudo = f"""
        {self._render_nav(cliente)}
        <section class="hero">
          <div>
            <div class="eyebrow">CRM e Painel Administrativo</div>
            <h1>Visão central da operação SaaS</h1>
            <p>Aqui você enxerga clientes do portal, planos vendidos, assinatura do sistema, mensalidades e saúde da base comercial.</p>
          </div>
          <div class="hero-side">
            <div class="meta-card">
              <div class="meta-label">Assinatura atual</div>
              <div class="meta-value"><span class="badge {badge_tipo}">{escape(badge_texto)}</span></div>
            </div>
            <div class="meta-card">
              <div class="meta-label">Plano vigente</div>
              <div class="meta-value">{escape(assinatura.get('plano_nome') or 'Nao definido')}</div>
            </div>
            <div class="meta-card">
              <div class="meta-label">Mensalidade</div>
              <div class="meta-value">{escape(_fmt_money(assinatura.get('valor_mensal', 0)))}</div>
            </div>
          </div>
        </section>
        <section class="grid">
          <article class="card span-3"><div class="kpi-label">Clientes</div><div class="kpi-value">{metricas['clientes']}</div></article>
          <article class="card span-3"><div class="kpi-label">Planos ativos</div><div class="kpi-value">{metricas['ativas']}</div></article>
          <article class="card span-3"><div class="kpi-label">Atrasados</div><div class="kpi-value">{metricas['atrasadas']}</div></article>
          <article class="card span-3"><div class="kpi-label">Cancelados</div><div class="kpi-value">{metricas['canceladas']}</div></article>
        </section>
        <section class="grid">
          <article class="card span-7">
            <h2 class="section-title">Assinatura do sistema</h2>
            <form method="post" action="/assinatura/salvar">
              <div class="form-grid">
                <label>Plano
                  <select name="plano_code">
                    {''.join(f"<option value='{escape(plano['code'])}' {'selected' if plano['code'] == assinatura.get('plano_code') else ''}>{escape(plano['nome'])}</option>" for plano in listar_planos_cobranca(apenas_ativos=False))}
                  </select>
                </label>
                <label>Status
                  <select name="status">
                    {''.join(f"<option value='{status}' {'selected' if status == (assinatura.get('status') or '').lower() else ''}>{_plan_badge(status)[0]}</option>" for status in ['development','trial','active','paid','blocked','suspended','cancelled'])}
                  </select>
                </label>
                <label>Próximo vencimento
                  <input type="datetime-local" name="next_due_at" value="{escape(_fmt_dt_local(assinatura.get('next_due_at')))}">
                </label>
                <label>Carência até
                  <input type="datetime-local" name="grace_until" value="{escape(_fmt_dt_local(assinatura.get('grace_until')))}">
                </label>
              </div>
              <div class="actions">
                <button class="btn-primary" type="submit">Salvar assinatura</button>
                <button class="btn-soft" type="submit" formaction="/cobrancas/gerar">Gerar cobrança do mês</button>
              </div>
            </form>
          </article>
          <article class="card span-5">
            <h2 class="section-title">Integrações e acessos</h2>
            <div class="api-box">GET /api/status
GET /api/assinatura
GET /api/cobrancas

Portal comercial:
http://{HOST}:{PORT}/

Admin:
http://{HOST}:{PORT}/admin</div>
          </article>
        </section>
        <section class="grid">
          <article class="card span-6">
            <h2 class="section-title">Clientes e assinaturas</h2>
            <table>
              <thead>
                <tr>
                  <th>Cliente</th>
                  <th>Plano</th>
                  <th>Status</th>
                  <th>Vencimento</th>
                </tr>
              </thead>
              <tbody>
                {''.join(linhas) or '<tr><td colspan="4">Nenhuma assinatura do portal encontrada.</td></tr>'}
              </tbody>
            </table>
          </article>
          <article class="card span-6">
            <h2 class="section-title">Mensalidades do sistema</h2>
            <table>
              <thead>
                <tr>
                  <th>Competência</th>
                  <th>Plano</th>
                  <th>Status</th>
                  <th>Valor</th>
                </tr>
              </thead>
              <tbody>
                {''.join(f"<tr><td>{int(c.get('referencia_mes',0)):02d}/{c.get('referencia_ano','')}</td><td>{escape(c.get('plano_nome') or c.get('plano_code') or '')}</td><td>{escape(_charge_badge(c.get('status'))[0])}</td><td>{escape(_fmt_money(c.get('valor', 0)))}</td></tr>" for c in cobrancas) or '<tr><td colspan=\"4\">Nenhuma cobrança do sistema encontrada.</td></tr>'}
              </tbody>
            </table>
          </article>
        </section>
        """
        return _layout(conteudo, titulo="Admin", mensagem=mensagem, erro=erro)

    def do_GET(self):
        parsed, query = self._query()
        cliente = self._cliente_logado()

        if parsed.path == "/":
            return self._html(self._render_home(query.get("msg", [""])[0], query.get("err", [""])[0]))
        if parsed.path == "/contratar":
            rendered = self._render_choose_plan(query.get("plan", [""])[0], query.get("msg", [""])[0], query.get("err", [""])[0])
            if isinstance(rendered, str):
                return self._html(rendered)
            return rendered
        if parsed.path == "/login":
            return self._html(self._render_auth_page("login", query.get("plan", [""])[0], query.get("err", [""])[0]))
        if parsed.path == "/cadastro":
            return self._html(self._render_auth_page("cadastro", query.get("plan", [""])[0], query.get("err", [""])[0]))
        if parsed.path == "/checkout":
            rendered = self._render_checkout(cliente, query.get("plan", [""])[0], query.get("err", [""])[0])
            if isinstance(rendered, str):
                return self._html(rendered)
            return rendered
        if parsed.path == "/checkout/pix":
            rendered = self._render_pix_checkout(cliente, query.get("id", ["0"])[0], query.get("err", [""])[0])
            if isinstance(rendered, str):
                return self._html(rendered)
            return rendered
        if parsed.path == "/checkout/cartao":
            rendered = self._render_card_checkout(cliente, query.get("id", ["0"])[0], query.get("err", [""])[0])
            if isinstance(rendered, str):
                return self._html(rendered)
            return rendered
        if parsed.path == "/portal":
            rendered = self._render_portal(cliente, query.get("msg", [""])[0], query.get("err", [""])[0])
            if isinstance(rendered, str):
                return self._html(rendered)
            return rendered
        if parsed.path == "/admin":
            return self._html(self._render_admin(query.get("msg", [""])[0], query.get("err", [""])[0]))
        if parsed.path == "/logout":
            cookies = self._parse_cookies()
            token = cookies.get("portal_session")
            if token and token in SESSIONS:
                SESSIONS.pop(token, None)
            return self._redirect("/?msg=" + urlencode({"": "Sessão encerrada com sucesso."})[1:], clear_cookie=True)

        if parsed.path == "/api/status":
            return self._json(avaliar_status_cobranca())
        if parsed.path == "/api/assinatura":
            return self._json(obter_assinatura_sistema() or {})
        if parsed.path == "/api/cobrancas":
            return self._json(listar_cobrancas_mensais(limit=60))

        self.send_error(404, "Rota nao encontrada.")

    def do_POST(self):
        parsed, _ = self._query()
        form = self._read_form()
        cliente = self._cliente_logado()

        try:
            if parsed.path == "/auth/login":
                resultado = autenticar_cliente_portal(form.get("email", ""), form.get("password", ""))
                if not resultado.get("ok"):
                    return self._redirect(
                        "/login?" + urlencode({"plan": form.get("plan", ""), "err": "Email ou senha inválidos."})
                    )
                cliente_portal = resultado["cliente"]
                token = secrets.token_urlsafe(24)
                SESSIONS[token] = cliente_portal["id"]
                destino = "/portal"
                if form.get("plan"):
                    destino = "/checkout?" + urlencode({"plan": form.get("plan", "")})
                return self._redirect(destino, cookie=_cookie_header("portal_session", token))

            if parsed.path == "/auth/register":
                if form.get("password", "") != form.get("password_confirm", ""):
                    return self._redirect(
                        "/cadastro?" + urlencode({"plan": form.get("plan", ""), "err": "As senhas não conferem."})
                    )
                cliente_portal = criar_cliente_portal(
                    nome=form.get("nome", ""),
                    email=form.get("email", ""),
                    password=form.get("password", ""),
                    telefone=form.get("telefone", ""),
                    documento=form.get("documento", ""),
                    endereco=form.get("endereco", ""),
                )
                token = secrets.token_urlsafe(24)
                SESSIONS[token] = cliente_portal["id"]
                destino = "/portal"
                if form.get("plan"):
                    destino = "/checkout?" + urlencode({"plan": form.get("plan", "")})
                return self._redirect(destino, cookie=_cookie_header("portal_session", token))

            if parsed.path == "/checkout/iniciar":
                if not cliente:
                    return self._redirect("/login?err=" + urlencode({"": "Faça login para seguir."})[1:])
                checkout = iniciar_checkout_portal(
                    cliente_id=cliente["id"],
                    plano_code=form.get("plan", ""),
                    payment_method=form.get("payment_method", ""),
                )
                rota_checkout = "/checkout/pix" if str(form.get("payment_method", "")).strip().lower() == "pix" else "/checkout/cartao"
                return self._redirect(rota_checkout + "?" + urlencode({"id": checkout["id"]}))

            if parsed.path == "/checkout/pix/aprovar":
                confirmar_pagamento_portal(
                    cobranca_id=form.get("checkout_id", "0"),
                    payment_method="pix",
                )
                return self._redirect("/portal?" + urlencode({"msg": "Pagamento PIX aprovado e plano ativado com sucesso."}))

            if parsed.path == "/checkout/cartao/processar":
                numero = "".join(ch for ch in str(form.get("card_number", "")) if ch.isdigit())
                checkout_id = form.get("checkout_id", "0")
                if not numero or numero.endswith("0000"):
                    atualizar_checkout_portal_status(
                        cobranca_id=checkout_id,
                        status="falhou",
                        payment_method="cartao",
                        external_ref="sandbox-card-declined",
                    )
                    return self._redirect("/checkout/cartao?" + urlencode({"id": checkout_id, "err": "Pagamento não autorizado. Revise os dados do cartão ou tente outra forma de pagamento."}))

                confirmar_pagamento_portal(
                    cobranca_id=checkout_id,
                    payment_method="cartao",
                )
                return self._redirect("/portal?" + urlencode({"msg": "Pagamento com cartão aprovado e plano ativado com sucesso."}))

            if parsed.path == "/checkout/cancelar":
                atualizar_checkout_portal_status(
                    cobranca_id=form.get("checkout_id", "0"),
                    status="cancelado",
                )
                return self._redirect("/portal?" + urlencode({"msg": "Checkout cancelado."}))

            if parsed.path == "/assinatura/salvar":
                salvar_assinatura_sistema(
                    plano_code=form.get("plano_code", ""),
                    status=form.get("status", "active"),
                    ciclo="mensal",
                    next_due_at=form.get("next_due_at", ""),
                    grace_until=form.get("grace_until", ""),
                )
                return self._redirect("/admin?" + urlencode({"msg": "Assinatura do sistema atualizada."}))

            if parsed.path == "/cobrancas/gerar":
                gerar_cobranca_mensal_atual()
                return self._redirect("/admin?" + urlencode({"msg": "Cobrança do sistema gerada com sucesso."}))

            if parsed.path == "/cobrancas/status":
                atualizar_status_cobranca(
                    cobranca_id=form.get("cobranca_id", "0"),
                    status=form.get("status", "pendente"),
                    payment_method=form.get("payment_method", ""),
                )
                return self._redirect("/admin?" + urlencode({"msg": "Status da cobrança atualizado."}))

            return self._redirect("/?err=" + urlencode({"": "Acao nao reconhecida."})[1:])
        except Exception as exc:
            destino = "/admin" if parsed.path in {"/assinatura/salvar", "/cobrancas/gerar", "/cobrancas/status"} else "/"
            if parsed.path == "/auth/login":
                destino = "/login"
            elif parsed.path == "/auth/register":
                destino = "/cadastro"
            elif parsed.path in {"/checkout/iniciar", "/checkout/pix/aprovar", "/checkout/cartao/processar", "/checkout/cancelar"}:
                destino = "/checkout"
            qs = {"err": str(exc)}
            if form.get("plan"):
                qs["plan"] = form.get("plan", "")
            if form.get("checkout_id"):
                qs["id"] = form.get("checkout_id", "")
            return self._redirect(destino + "?" + urlencode(qs))


def run_server(host=HOST, port=PORT):
    criar_banco()
    server = ThreadingHTTPServer((host, port), BillingHandler)
    print(f"Billing site rodando em http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
