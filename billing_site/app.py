import json
import logging
import os
import secrets
from html import escape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as HttpRequest, urlopen

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from billing_site.server import (
    PLAN_CONTENT,
    _charge_badge,
    _fmt_dt_local,
    _fmt_money,
    _layout,
    _plan_badge,
)
from database.db import (
    atualizar_checkout_portal_status,
    atualizar_checkout_portal_gateway,
    atualizar_status_cobranca,
    autenticar_cliente_portal,
    autenticar_usuario,
    avaliar_status_cobranca,
    carregar_config,
    confirmar_pagamento_portal,
    contar_usuarios,
    criar_banco,
    criar_cliente_portal,
    criar_usuario,
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
    obter_cliente_portal_por_email,
    obter_metricas_portal,
    salvar_config,
    salvar_assinatura_sistema,
)


APP_HOST = os.environ.get("BILLING_SITE_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("BILLING_SITE_PORT", "8765"))
PUBLIC_BASE_URL = os.environ.get("BILLING_SITE_PUBLIC_URL", f"http://{APP_HOST}:{APP_PORT}")
SECURE_COOKIES = os.environ.get("BILLING_SITE_SECURE_COOKIES", "0").strip() in {"1", "true", "True"}

CLIENT_SESSIONS = {}
ADMIN_SESSIONS = {}
TEST_BUYER_EMAIL = "comprador@testuser.com"
TEST_BUYER_PASSWORD = "1234"

app = FastAPI(title="MBS Fiscal Portal", docs_url=None, redoc_url=None)

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
MP_LOGGER = logging.getLogger("billing_site.mercadopago")
if not MP_LOGGER.handlers:
    MP_LOGGER.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_DIR / "mercadopago_portal.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    MP_LOGGER.addHandler(handler)


def _base_url():
    return PUBLIC_BASE_URL.rstrip("/")


def _html(page: str):
    return HTMLResponse(page)


def _redirect(path: str):
    return RedirectResponse(url=path, status_code=303)


def _set_cookie(response: RedirectResponse, name: str, value: str, max_age: int = 86400):
    response.set_cookie(
        key=name,
        value=value,
        max_age=max_age,
        path="/",
        httponly=True,
        samesite="lax",
        secure=SECURE_COOKIES,
    )


def _clear_cookie(response: RedirectResponse, name: str):
    response.delete_cookie(
        key=name,
        path="/",
        httponly=True,
        samesite="lax",
        secure=SECURE_COOKIES,
    )


def _ensure_test_buyer():
    cliente = obter_cliente_portal_por_email(TEST_BUYER_EMAIL)
    if cliente:
        return cliente
    return criar_cliente_portal(
        nome="Comprador Teste",
        email=TEST_BUYER_EMAIL,
        password=TEST_BUYER_PASSWORD,
    )


def _cliente_logado(request: Request):
    token = request.cookies.get("portal_session", "")
    cliente_id = CLIENT_SESSIONS.get(token)
    if not cliente_id:
        return None
    return obter_cliente_portal(cliente_id)


def _admin_logado(request: Request):
    token = request.cookies.get("portal_admin_session", "")
    return ADMIN_SESSIONS.get(token)


def _require_admin(request: Request):
    admin = _admin_logado(request)
    if not admin or admin.get("role") != "admin":
        return None
    return admin


def _admin_bootstrap_needed():
    return contar_usuarios() == 0


def _mercadopago_config():
    config = carregar_config()
    environment = str(config.get("mp_environment", "sandbox") or "sandbox").strip().lower()
    sandbox = environment != "production"
    return {
        "environment": "sandbox" if sandbox else "production",
        "public_key": (config.get("mp_public_key_test" if sandbox else "mp_public_key_prod") or "").strip(),
        "access_token": (config.get("mp_access_token_test" if sandbox else "mp_access_token_prod") or "").strip(),
    }


def _mercadopago_ready():
    cfg = _mercadopago_config()
    return bool(cfg["public_key"] and cfg["access_token"])


def _mercadopago_request(method: str, path: str, payload=None):
    cfg = _mercadopago_config()
    if not cfg["access_token"]:
        raise ValueError("Credenciais do Mercado Pago nao configuradas para o ambiente ativo.")
    headers = {
        "Authorization": f"Bearer {cfg['access_token']}",
        "Content-Type": "application/json",
    }
    if cfg["environment"] == "sandbox":
        headers["X-scope"] = "stage"
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = HttpRequest(
        url=f"https://api.mercadopago.com{path}",
        data=body,
        headers=headers,
        method=method.upper(),
    )
    MP_LOGGER.info(
        "request method=%s path=%s environment=%s payload=%s",
        method.upper(),
        path,
        cfg["environment"],
        json.dumps(payload or {}, ensure_ascii=True),
    )
    try:
        with urlopen(request, timeout=20) as response:
            content = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        MP_LOGGER.error(
            "http_error method=%s path=%s status=%s environment=%s detail=%s",
            method.upper(),
            path,
            exc.code,
            cfg["environment"],
            detail or exc.reason,
        )
        if int(exc.code) == 503:
            raise ValueError(
                "Mercado Pago temporariamente indisponivel no ambiente de teste. Aguarde alguns instantes e tente novamente."
            ) from exc
        raise ValueError(f"Mercado Pago respondeu com erro {exc.code}: {detail or exc.reason}") from exc
    except URLError as exc:
        MP_LOGGER.error(
            "url_error method=%s path=%s environment=%s reason=%s",
            method.upper(),
            path,
            cfg["environment"],
            exc.reason,
        )
        raise ValueError(f"Nao foi possivel conectar ao Mercado Pago: {exc.reason}") from exc
    MP_LOGGER.info(
        "response method=%s path=%s environment=%s body=%s",
        method.upper(),
        path,
        cfg["environment"],
        content,
    )
    return json.loads(content) if content else {}


def _mercadopago_criar_assinatura(checkout):
    cfg = _mercadopago_config()
    payer_email = str(checkout.get("cliente_email") or "").strip().lower()
    if cfg["environment"] == "sandbox" and not payer_email.endswith("@testuser.com"):
        raise ValueError(
            "No ambiente de teste do Mercado Pago, o checkout precisa usar um comprador de teste com email terminando em @testuser.com."
        )
    payload = {
        "reason": f"{checkout.get('plano_nome') or 'Plano MBS Fiscal'}",
        "external_reference": str(checkout.get("id")),
        "payer_email": payer_email,
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": float(checkout.get("valor", 0) or 0),
            "currency_id": "BRL",
        },
        "back_url": f"{_base_url()}/checkout/mercadopago/retorno?checkout_id={int(checkout.get('id', 0))}",
        "status": "pending",
    }
    return _mercadopago_request("POST", "/preapproval", payload)


def _mercadopago_criar_pagamento_unico(checkout):
    cfg = _mercadopago_config()
    payer_email = str(checkout.get("cliente_email") or "").strip().lower()
    if cfg["environment"] == "sandbox" and not payer_email.endswith("@testuser.com"):
        raise ValueError(
            "No ambiente de teste do Mercado Pago, o checkout precisa usar um comprador de teste com email terminando em @testuser.com."
        )
    retorno = f"{_base_url()}/checkout/mercadopago/retorno?checkout_id={int(checkout.get('id', 0))}"
    payload = {
        "items": [
            {
                "id": str(checkout.get("plano_code") or checkout.get("id") or "plano"),
                "title": f"{checkout.get('plano_nome') or 'Plano MBS Fiscal'}",
                "description": "Contratacao do plano MBS Fiscal",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": float(checkout.get("valor", 0) or 0),
            }
        ],
        "payer": {"email": payer_email},
        "external_reference": str(checkout.get("id")),
        "back_urls": {
            "success": retorno,
            "failure": retorno,
            "pending": retorno,
        },
        "payment_methods": {
            "default_payment_method_id": "pix",
            "excluded_payment_types": [
                {"id": "credit_card"},
                {"id": "debit_card"},
                {"id": "ticket"},
            ],
            "installments": 1,
        },
    }
    return _mercadopago_request("POST", "/checkout/preferences", payload)


def _mercadopago_obter_assinatura(preapproval_id: str):
    return _mercadopago_request("GET", f"/preapproval/{preapproval_id}")


def _mercadopago_obter_pagamento(payment_id: str):
    return _mercadopago_request("GET", f"/v1/payments/{payment_id}")


def _mercadopago_buscar_pagamento_por_referencia(external_reference: str):
    query = urlencode(
        {
            "external_reference": str(external_reference or "").strip(),
            "sort": "date_created",
            "criteria": "desc",
        }
    )
    resposta = _mercadopago_request("GET", f"/v1/payments/search?{query}")
    pagamentos = resposta.get("results") or []
    return pagamentos[0] if pagamentos else None


def _aplicar_pagamento_mercadopago(cobranca, pagamento_mp, fallback_status=""):
    pagamento_id = str((pagamento_mp or {}).get("id") or "").strip()
    mp_status = str((pagamento_mp or {}).get("status") or fallback_status or "").strip().lower()
    metodo = cobranca.get("payment_method") or "mercadopago"
    if mp_status == "approved":
        confirmar_pagamento_portal(cobranca_id=cobranca["id"], payment_method=metodo)
        return "aprovado"
    if mp_status in {"cancelled", "rejected"}:
        atualizar_checkout_portal_status(
            cobranca_id=cobranca["id"],
            status="falhou",
            payment_method=metodo,
            external_ref=pagamento_id or cobranca.get("external_ref") or "",
        )
        return "falhou"
    atualizar_checkout_portal_status(
        cobranca_id=cobranca["id"],
        status="pendente",
        payment_method=metodo,
        external_ref=pagamento_id or cobranca.get("external_ref") or "",
    )
    return mp_status or "pendente"


def _is_mercadopago_checkout(checkout):
    return bool((checkout or {}).get("external_ref"))


def _render_nav(cliente=None, admin=None):
    if admin:
        admin_links = '<a href="/admin" class="primary">Admin</a><a href="/admin/logout">Sair do admin</a>'
    else:
        admin_destino = "/admin/bootstrap" if _admin_bootstrap_needed() else "/admin/login"
        admin_links = f'<a href="{admin_destino}">Admin</a>'
    cliente_links = (
        '<a href="/portal" class="primary">Area do usuario</a>'
        '<a href="/logout">Sair</a>'
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
          <div class="small">Planos, cobranca e portal do cliente</div>
        </div>
      </div>
      <div class="nav-links">
        <a href="/">Planos</a>
        {admin_links}
        {cliente_links}
      </div>
    </div>
    """


def _pix_code(checkout):
    token = checkout.get("checkout_token") or secrets.token_hex(8)
    valor = f"{float(checkout.get('valor', 0) or 0):.2f}"
    return (
        "00020126580014BR.GOV.BCB.PIX0136"
        f"{token}520400005303986540{len(valor):02d}{valor}"
        "5802BR5913MBS FISCAL6009FORTALEZA62070503***6304ABCD"
    )


def _render_home(request: Request, mensagem="", erro=""):
    cliente = _cliente_logado(request)
    admin = _admin_logado(request)
    planos = listar_planos_cobranca(apenas_ativos=True)
    plan_cards = []
    for idx, plano in enumerate(planos):
        conteudo_plano = PLAN_CONTENT.get(plano.get("code"), {})
        recursos = "".join(
            f"<li>{escape(str(recurso).replace('_', ' ').title())}</li>"
            for recurso in plano.get("recursos", [])
        )
        ganhos = "".join(f"<li>{escape(item)}</li>" for item in conteudo_plano.get("gains", []))
        featured = "featured" if idx == len(planos) - 1 else ""
        plan_cards.append(
            f"""
            <article class="plan {featured}">
              <div class="badge info">{escape(plano.get('code', ''))}</div>
              <h3>{escape(plano.get('nome', 'Plano'))}</h3>
              <div class="plan-price">{escape(_fmt_money(plano.get('valor_mensal', 0)))}</div>
              <div class="small"><strong>{escape(conteudo_plano.get('headline', 'Plano pronto para operacao fiscal.'))}</strong></div>
              <div class="small">{escape(conteudo_plano.get('pitch', 'Ciclo mensal com liberacao dos recursos do sistema conforme o plano contratado.'))}</div>
              <div class="small">O que o cliente ganha:</div>
              <ul>{ganhos or recursos}</ul>
              <a class="button btn-primary" href="/contratar?plan={escape(plano.get('code', ''))}">Escolher plano</a>
            </article>
            """
        )
    conteudo = f"""
    {_render_nav(cliente, admin)}
    <section class="hero">
      <div>
        <div class="eyebrow">Portal Comercial</div>
        <h1>Escolha o plano ideal, conclua a contratacao e acompanhe sua assinatura</h1>
        <p>Este portal reune a vitrine dos planos, autenticacao do cliente, contratacao, checkout e area do usuario com assinatura ativa, historico financeiro e recursos liberados.</p>
        <div class="steps">
          <div class="step"><strong>1. Escolha o plano</strong><div class="small">O cliente comeca pela pagina inicial e seleciona a oferta ideal.</div></div>
          <div class="step"><strong>2. Entre ou cadastre-se</strong><div class="small">Se ja tiver conta, faz login. Se nao, cria a conta com os dados do portal.</div></div>
          <div class="step"><strong>3. Checkout</strong><div class="small">Depois do cadastro, escolhe PIX ou cartao e entra na area do usuario.</div></div>
        </div>
      </div>
      <div class="hero-side">
        <div class="meta-card">
          <div class="meta-label">Operacao</div>
          <div class="meta-value">Portal online</div>
        </div>
        <div class="meta-card">
          <div class="meta-label">Portal do cliente</div>
          <div class="meta-value">{escape(cliente.get('nome')) if cliente else 'Nao autenticado'}</div>
        </div>
        <div class="meta-card">
          <div class="meta-label">Proximo passo</div>
          <div class="meta-value">{'Ir para checkout' if cliente else 'Escolher plano'}</div>
        </div>
      </div>
    </section>
    <section class="grid">
      <article class="card span-12">
        <h2 class="section-title">Planos disponiveis</h2>
        <p class="subtitle">Cada plano foi apresentado para conduzir o cliente da escolha ate a ativacao, com posicionamento comercial claro e foco em conversao.</p>
        <div class="plans">{''.join(plan_cards)}</div>
      </article>
    </section>
    """
    return _layout(conteudo, mensagem=mensagem, erro=erro)


def _render_auth_page(request: Request, modo="login", plano_code="", erro=""):
    cliente = _cliente_logado(request)
    admin = _admin_logado(request)
    planos = {plano["code"]: plano for plano in listar_planos_cobranca(apenas_ativos=True)}
    plano = planos.get(plano_code) if plano_code else None
    titulo = "Entrar na conta" if modo == "login" else "Criar conta"
    subtitulo = (
        "Entre com seu email para continuar a contratacao do plano."
        if modo == "login"
        else "Cadastre os dados do cliente para seguir para o checkout."
    )
    plano_box = ""
    if plano:
        plano_box = f"""
        <div class="checkout-option">
          <div class="badge info">Plano selecionado</div>
          <h3 style="margin:10px 0 6px;">{escape(plano.get('nome', 'Plano'))}</h3>
          <div class="small">{escape(_fmt_money(plano.get('valor_mensal', 0)))} por mes</div>
        </div>
        """
    admin_test_action = ""
    if admin and plano:
        if _mercadopago_config()["environment"] == "sandbox":
            admin_test_action = f"""
            <div class="checkout-option" style="margin-bottom:16px;">
              <div class="small"><strong>Voce esta no painel administrativo.</strong> Para testar no sandbox, entre como cliente de teste do portal.</div>
              <form method="post" action="/admin/testar-como-cliente" style="margin-top:12px;">
                <input type="hidden" name="plan" value="{escape(plano_code)}">
                <button class="btn-primary" type="submit">Usar cliente de teste e continuar</button>
              </form>
            </div>
            """
        else:
            admin_test_action = """
            <div class="checkout-option" style="margin-bottom:16px;">
              <div class="small"><strong>Mercado Pago em producao.</strong> Entre ou cadastre um cliente real do portal para fazer uma compra real.</div>
            </div>
            """
    if modo == "login":
        form = f"""
        {admin_test_action}
        <form method="post" action="/auth/login">
          <input type="hidden" name="plan" value="{escape(plano_code)}">
          <label>Email<input type="email" name="email" required></label>
          <label>Senha<input type="password" name="password" required></label>
          <div class="actions">
            <button class="btn-primary" type="submit">Entrar e continuar</button>
            <a class="button btn-soft" href="/cadastro?plan={escape(plano_code)}">Ainda nao tenho conta</a>
          </div>
        </form>
        """
    else:
        form = f"""
        {admin_test_action}
        <form method="post" action="/auth/register">
          <input type="hidden" name="plan" value="{escape(plano_code)}">
          <div class="form-grid">
            <label>Nome completo<input type="text" name="nome" required></label>
            <label>Email<input type="email" name="email" required></label>
            <label>Telefone<input type="text" name="telefone"></label>
            <label>Documento<input type="text" name="documento"></label>
          </div>
          <label>Endereco<textarea name="endereco"></textarea></label>
          <div class="form-grid">
            <label>Senha<input type="password" name="password" required></label>
            <label>Confirme a senha<input type="password" name="password_confirm" required></label>
          </div>
          <div class="actions">
            <button class="btn-primary" type="submit">Criar conta e continuar</button>
            <a class="button btn-soft" href="/login?plan={escape(plano_code)}">Ja tenho conta</a>
          </div>
        </form>
        """
    conteudo = f"""
    {_render_nav(cliente, admin)}
    <section class="grid">
      <article class="card span-7">
        <h1 style="font-size:34px;margin-bottom:10px;">{escape(titulo)}</h1>
        <p class="subtitle">{escape(subtitulo)}</p>
        {form}
      </article>
      <article class="card span-5">
        <h2 class="section-title">Fluxo da contratacao</h2>
        <div class="small">Escolha do plano -> login ou cadastro -> checkout -> area do usuario.</div>
        <div style="margin-top:14px;">{plano_box}</div>
      </article>
    </section>
    """
    return _layout(conteudo, titulo=titulo, erro=erro)


def _render_choose_plan(request: Request, plano_code="", mensagem="", erro=""):
    cliente = _cliente_logado(request)
    admin = _admin_logado(request)
    planos = {plano["code"]: plano for plano in listar_planos_cobranca(apenas_ativos=True)}
    plano = planos.get(plano_code)
    if not plano:
        return _render_home(request, erro="Plano nao encontrado.")
    conteudo_plano = PLAN_CONTENT.get(plano_code, {})
    if cliente:
        return _redirect(f"/checkout?plan={plano_code}")
    admin_test_action = ""
    if admin:
        if _mercadopago_config()["environment"] == "sandbox":
            admin_test_action = f"""
            <form method="post" action="/admin/testar-como-cliente">
              <input type="hidden" name="plan" value="{escape(plano_code)}">
              <button class="btn-primary" type="submit">Usar cliente de teste e ir ao checkout</button>
            </form>
            """
        else:
            admin_test_action = '<div class="small">Em producao, use um cadastro real de cliente para testar a compra.</div>'
    conteudo = f"""
    {_render_nav(cliente, admin)}
    <section class="grid">
      <article class="card span-7">
        <div class="badge info">Plano escolhido</div>
        <h1 style="font-size:34px;margin:12px 0 10px;">{escape(plano.get('nome', 'Plano'))}</h1>
        <p class="subtitle">Antes de seguir para o pagamento, o cliente pode entrar com a conta existente ou concluir um novo cadastro em poucos passos.</p>
        <div class="actions">
          {admin_test_action}
          <a class="button btn-primary" href="/login?plan={escape(plano_code)}">Ja tenho login</a>
          <a class="button btn-soft" href="/cadastro?plan={escape(plano_code)}">Ainda nao tenho conta</a>
        </div>
      </article>
      <article class="card span-5">
        <h2 class="section-title">Resumo da oferta</h2>
        <div class="plan featured">
          <h3>{escape(plano.get('nome', 'Plano'))}</h3>
          <div class="plan-price">{escape(_fmt_money(plano.get('valor_mensal', 0)))}</div>
          <div class="small"><strong>{escape(conteudo_plano.get('headline', ''))}</strong></div>
          <div class="small">{escape(conteudo_plano.get('pitch', ''))}</div>
          <ul>{''.join(f"<li>{escape(item)}</li>" for item in conteudo_plano.get('gains', []))}</ul>
        </div>
      </article>
    </section>
    """
    return _layout(conteudo, mensagem=mensagem, erro=erro)


def _render_checkout(request: Request, cliente, plano_code="", erro=""):
    admin = _admin_logado(request)
    planos = {plano["code"]: plano for plano in listar_planos_cobranca(apenas_ativos=True)}
    plano = planos.get(plano_code)
    if not plano:
        return _render_home(request, erro="Plano nao encontrado para checkout.")
    mp_cfg = _mercadopago_config()
    mp_ready = _mercadopago_ready()
    mp_note = ""
    if mp_ready:
        ambiente = "Sandbox / Teste" if mp_cfg["environment"] == "sandbox" else "Producao"
        mp_help = (
            'No sandbox, use um comprador de teste do Mercado Pago. O email do cliente do portal precisa terminar com <strong>@testuser.com</strong>.'
            if mp_cfg["environment"] == "sandbox"
            else "Em producao, use um cliente real do portal e um comprador real do Mercado Pago. Nao use emails <strong>@testuser.com</strong>."
        )
        mp_note = f"""
        <div class="checkout-option" style="margin-bottom:16px;">
          <div class="small"><strong>Mercado Pago ativo:</strong> o checkout vai abrir no ambiente oficial do Mercado Pago em <strong>{ambiente}</strong>.</div>
          <div class="small">{mp_help}</div>
        </div>
        """
    conteudo = f"""
    {_render_nav(cliente, admin)}
    <section class="grid">
      <article class="card span-7">
        <h1 style="font-size:34px;margin-bottom:10px;">Checkout do plano</h1>
        <p class="subtitle">Escolha a forma de pagamento e siga para a etapa correspondente. O fluxo ja esta organizado para PIX e cartao em jornadas separadas.</p>
        {mp_note}
        <form method="post" action="/checkout/iniciar">
          <input type="hidden" name="plan" value="{escape(plano_code)}">
          <div class="checkout-methods">
            <div class="checkout-option">
              <label><input type="radio" name="payment_method" value="pix" checked> PIX</label>
              <div class="small">Exibe QR Code, codigo copia e cola e status da cobranca para acompanhar a confirmacao do pagamento.</div>
            </div>
            <div class="checkout-option">
              <label><input type="radio" name="payment_method" value="cartao"> Cartao</label>
              <div class="small">Abre o formulario de cartao para concluir a contratacao com rapidez e seguranca.</div>
            </div>
          </div>
          <div class="actions">
            <button class="btn-primary" type="submit">Continuar para o metodo escolhido</button>
            <a class="button btn-soft" href="/portal">Voltar para area do usuario</a>
          </div>
        </form>
      </article>
      <article class="card span-5">
        <h2 class="section-title">Resumo da contratacao</h2>
        <div class="meta-card"><div class="meta-label">Cliente</div><div class="meta-value">{escape(cliente.get('nome', ''))}</div></div>
        <div class="meta-card" style="margin-top:12px;"><div class="meta-label">Plano</div><div class="meta-value">{escape(plano.get('nome', 'Plano'))}</div></div>
        <div class="meta-card" style="margin-top:12px;"><div class="meta-label">Valor</div><div class="meta-value">{escape(_fmt_money(plano.get('valor_mensal', 0)))}</div></div>
      </article>
    </section>
    """
    return _layout(conteudo, titulo="Checkout", erro=erro)


def _render_pix_checkout(request: Request, cliente, checkout_id, erro=""):
    admin = _admin_logado(request)
    checkout = obter_checkout_portal(checkout_id)
    if not checkout or int(checkout.get("cliente_id", 0)) != int(cliente["id"]):
        return _render_portal(request, cliente, erro="Checkout PIX nao encontrado.")
    badge_texto, badge_tipo = _charge_badge(checkout.get("status"))
    if _is_mercadopago_checkout(checkout):
        continue_button = ""
        if checkout.get("gateway_checkout_url"):
            continue_button = f'<a class="button btn-primary" href="/checkout/mercadopago/continuar?id={int(checkout.get("id", 0))}">Continuar no Mercado Pago</a>'
        conteudo = f"""
        {_render_nav(cliente, admin)}
        <section class="grid">
          <article class="card span-7">
            <div class="status-line">
              <div>
                <h1 style="font-size:34px;margin:0 0 10px;">Pagamento via Mercado Pago</h1>
                <p class="subtitle">Esse checkout foi criado no Mercado Pago. Continue o pagamento no ambiente oficial ou consulte o status atualizado da assinatura.</p>
              </div>
              <span class="badge {badge_tipo}">{escape(badge_texto)}</span>
            </div>
            <div class="checkout-option" style="margin-top:18px;">
              <div class="small"><strong>Checkout externo:</strong> use o botao abaixo para voltar ao Mercado Pago e concluir o pagamento com seguranca.</div>
            </div>
            <div class="actions">
              {continue_button}
              <a class="button btn-soft" href="/checkout/mercadopago/verificar?id={int(checkout.get('id', 0))}">Verificar status do pagamento</a>
              <form method="post" action="/checkout/cancelar">
                <input type="hidden" name="checkout_id" value="{int(checkout.get('id', 0))}">
                <button class="btn-soft" type="submit">Cancelar checkout</button>
              </form>
            </div>
          </article>
          <article class="card span-5">
            <h2 class="section-title">Resumo do pedido</h2>
            <div class="meta-card"><div class="meta-label">Plano</div><div class="meta-value">{escape(checkout.get('plano_nome') or '')}</div></div>
            <div class="meta-card" style="margin-top:12px;"><div class="meta-label">Valor</div><div class="meta-value">{escape(_fmt_money(checkout.get('valor', 0)))}</div></div>
            <div class="meta-card" style="margin-top:12px;"><div class="meta-label">Vencimento</div><div class="meta-value">{escape(_fmt_dt_local(checkout.get('due_at')) or '-')}</div></div>
          </article>
        </section>
        """
        return _layout(conteudo, titulo="Pagamento via Mercado Pago", erro=erro)
    migrate_button = ""
    if _mercadopago_ready():
        migrate_button = f'<a class="button btn-primary" href="/checkout/mercadopago/iniciar?id={int(checkout.get("id", 0))}">Continuar no Mercado Pago</a>'
    conteudo = f"""
    {_render_nav(cliente, admin)}
    <section class="grid">
      <article class="card span-7">
        <div class="status-line">
          <div>
            <h1 style="font-size:34px;margin:0 0 10px;">Pagamento via PIX</h1>
            <p class="subtitle">Use o QR Code ou o codigo copia e cola para concluir a contratacao e ativar o seu plano com agilidade.</p>
          </div>
          <span class="badge {badge_tipo}">{escape(badge_texto)}</span>
        </div>
        <div class="qr-box"><div class="qr-core">PIX</div></div>
        <p class="small" style="margin-top:16px;">Apresente este QR Code no aplicativo do banco ou utilize o codigo copia e cola para concluir o pagamento.</p>
        <div class="code-box">{escape(_pix_code(checkout))}</div>
        <div class="actions">
          {migrate_button}
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
        <div class="meta-card"><div class="meta-label">Plano</div><div class="meta-value">{escape(checkout.get('plano_nome') or '')}</div></div>
        <div class="meta-card" style="margin-top:12px;"><div class="meta-label">Valor</div><div class="meta-value">{escape(_fmt_money(checkout.get('valor', 0)))}</div></div>
        <div class="meta-card" style="margin-top:12px;"><div class="meta-label">Vencimento</div><div class="meta-value">{escape(_fmt_dt_local(checkout.get('due_at')) or '-')}</div></div>
      </article>
    </section>
    """
    return _layout(conteudo, titulo="Pagamento via PIX", erro=erro)


def _render_card_checkout(request: Request, cliente, checkout_id, erro=""):
    admin = _admin_logado(request)
    checkout = obter_checkout_portal(checkout_id)
    if not checkout or int(checkout.get("cliente_id", 0)) != int(cliente["id"]):
        return _render_portal(request, cliente, erro="Checkout de cartao nao encontrado.")
    badge_texto, badge_tipo = _charge_badge(checkout.get("status"))
    conteudo = f"""
    {_render_nav(cliente, admin)}
    <section class="grid">
      <article class="card span-7">
        <div class="status-line">
          <div>
            <h1 style="font-size:34px;margin:0 0 10px;">Pagamento por cartao</h1>
            <p class="subtitle">Preencha os dados do cartao para concluir a contratacao e liberar o acesso ao plano selecionado.</p>
          </div>
          <span class="badge {badge_tipo}">{escape(badge_texto)}</span>
        </div>
        <form method="post" action="/checkout/cartao/processar">
          <input type="hidden" name="checkout_id" value="{int(checkout.get('id', 0))}">
          <div class="form-grid">
            <label>Nome no cartao<input type="text" name="card_name" value="{escape(cliente.get('nome', ''))}" required></label>
            <label>Numero do cartao<input type="text" name="card_number" placeholder="4111 1111 1111 1111" required></label>
            <label>Validade<input type="text" name="card_expiry" placeholder="12/30" required></label>
            <label>CVV<input type="text" name="card_cvv" placeholder="123" required></label>
          </div>
          <div class="small">Apos a aprovacao, a assinatura e ativada e o historico financeiro fica disponivel na area do usuario.</div>
          <div class="actions">
            <button class="btn-primary" type="submit">Processar pagamento</button>
            <a class="button btn-soft" href="/portal">Voltar para area do usuario</a>
          </div>
        </form>
      </article>
      <article class="card span-5">
        <h2 class="section-title">Resumo do pedido</h2>
        <div class="meta-card"><div class="meta-label">Plano</div><div class="meta-value">{escape(checkout.get('plano_nome') or '')}</div></div>
        <div class="meta-card" style="margin-top:12px;"><div class="meta-label">Valor</div><div class="meta-value">{escape(_fmt_money(checkout.get('valor', 0)))}</div></div>
        <div class="meta-card" style="margin-top:12px;"><div class="meta-label">Forma</div><div class="meta-value">Cartao</div></div>
      </article>
    </section>
    """
    return _layout(conteudo, titulo="Pagamento por cartao", erro=erro)


def _render_portal(request: Request, cliente, mensagem="", erro=""):
    admin = _admin_logado(request)
    assinatura = obter_assinatura_portal_ativa(cliente["id"], incluir_checkout=True)
    cobrancas = listar_cobrancas_portal_cliente(cliente["id"], limit=24)
    cobranca_pendente = next(
        (c for c in cobrancas if str(c.get("status") or "").strip().lower() == "pendente"),
        None,
    )
    badge_texto, badge_tipo = _plan_badge(assinatura.get("status") if assinatura else "checkout")
    if assinatura:
        recursos = "".join(
            f"<li>{escape(str(recurso).replace('_', ' ').title())}</li>"
            for recurso in assinatura.get("recursos", [])
        )
        pending_action = ""
        if cobranca_pendente:
            if _is_mercadopago_checkout(cobranca_pendente):
                pending_action = f"""
                <div class="actions" style="margin-top:16px;">
                  <a class="button btn-primary" href="/checkout/mercadopago/continuar?id={int(cobranca_pendente.get('id', 0))}">Continuar no Mercado Pago</a>
                  <a class="button btn-soft" href="/checkout/mercadopago/verificar?id={int(cobranca_pendente.get('id', 0))}">Verificar status</a>
                </div>
                """
            else:
                pending_action = f"""
            <div class="actions" style="margin-top:16px;">
              <a class="button btn-primary" href="/checkout/retomar?id={int(cobranca_pendente.get('id', 0))}">Continuar pagamento pendente</a>
            </div>
            """
        assinatura_box = f"""
        <div class="plan featured">
          <div class="badge {badge_tipo}">{escape(badge_texto)}</div>
          <h3>{escape(assinatura.get('plano_nome', 'Plano'))}</h3>
          <div class="plan-price">{escape(_fmt_money(assinatura.get('valor_mensal', 0)))}</div>
          <div class="small">Proximo vencimento: {escape(assinatura.get('next_due_at') or 'Ainda nao definido')}</div>
          <ul>{recursos}</ul>
          {pending_action}
        </div>
        """
    else:
        assinatura_box = """
        <div class="checkout-option">
          <div class="small">Voce ainda nao tem uma assinatura ativa. Escolha um plano para iniciar a contratacao.</div>
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
    {_render_nav(cliente, admin)}
    <section class="grid">
      <article class="card span-4">
        <h2 class="section-title">Area do usuario</h2>
        <div class="small">Cliente autenticado e pronto para contratar, renovar ou consultar o historico.</div>
        <div style="margin-top:14px;">
          <div class="meta-card"><div class="meta-label">Nome</div><div class="meta-value">{escape(cliente.get('nome', ''))}</div></div>
          <div class="meta-card" style="margin-top:12px;"><div class="meta-label">Email</div><div class="meta-value">{escape(cliente.get('email', ''))}</div></div>
          <div class="meta-card" style="margin-top:12px;"><div class="meta-label">Telefone</div><div class="meta-value">{escape(cliente.get('telefone') or 'Nao informado')}</div></div>
        </div>
        <div class="actions" style="margin-top:16px;"><a class="button btn-primary" href="/">Contratar outro plano</a></div>
      </article>
      <article class="card span-8">
        <h2 class="section-title">Plano ativo e historico</h2>
        <p class="subtitle">Depois do pagamento aprovado, o cliente fica nesta area com o plano ativo e o historico financeiro.</p>
        {assinatura_box}
        <table>
          <thead><tr><th>Plano</th><th>Competencia</th><th>Valor</th><th>Status</th><th>Pagamento</th><th>Pago em</th></tr></thead>
          <tbody>{''.join(linhas) or '<tr><td colspan="6">Nenhum pagamento encontrado ainda.</td></tr>'}</tbody>
        </table>
      </article>
    </section>
    """
    return _layout(conteudo, titulo="Area do usuario", mensagem=mensagem, erro=erro)


def _render_admin_login(request: Request, erro=""):
    cliente = _cliente_logado(request)
    admin = _admin_logado(request)
    conteudo = f"""
    {_render_nav(cliente, admin)}
    <section class="grid">
      <article class="card span-7">
        <h1 style="font-size:34px;margin-bottom:10px;">Acesso administrativo</h1>
        <p class="subtitle">Entre com o usuario administrador do sistema para acessar o CRM e o painel de cobranca.</p>
        <form method="post" action="/admin/login">
          <label>Login do administrador<input type="text" name="username" required></label>
          <label>Senha<input type="password" name="password" required></label>
          <div class="actions"><button class="btn-primary" type="submit">Entrar no painel</button></div>
        </form>
      </article>
      <article class="card span-5">
        <h2 class="section-title">Acesso restrito</h2>
        <div class="small">Somente administradores aprovados podem visualizar clientes, assinaturas, cobrancas e configuracoes comerciais do portal.</div>
      </article>
    </section>
    """
    return _layout(conteudo, titulo="Admin login", erro=erro)


def _render_admin_bootstrap(request: Request, erro=""):
    cliente = _cliente_logado(request)
    admin = _admin_logado(request)
    conteudo = f"""
    {_render_nav(cliente, admin)}
    <section class="grid">
      <article class="card span-7">
        <h1 style="font-size:34px;margin-bottom:10px;">Criar administrador inicial</h1>
        <p class="subtitle">Como esta e a primeira configuracao do portal, crie agora o administrador principal que vai acessar o CRM, o painel de cobranca e as integracoes comerciais.</p>
        <form method="post" action="/admin/bootstrap">
          <label>Nome completo<input type="text" name="nome" required></label>
          <label>Email de acesso<input type="email" name="username" required></label>
          <div class="form-grid">
            <label>Senha<input type="password" name="password" required></label>
            <label>Confirmar senha<input type="password" name="password_confirm" required></label>
          </div>
          <div class="actions"><button class="btn-primary" type="submit">Criar administrador inicial</button></div>
        </form>
      </article>
      <article class="card span-5">
        <h2 class="section-title">Instalacao inicial</h2>
        <div class="small">Essa etapa so aparece enquanto nao existir nenhum usuario do sistema. Depois do primeiro administrador criado, o acesso volta a ser feito pela tela normal de login administrativo.</div>
      </article>
    </section>
    """
    return _layout(conteudo, titulo="Criar administrador inicial", erro=erro)


def _render_admin(request: Request, admin_user, mensagem="", erro=""):
    cliente = _cliente_logado(request)
    assinatura = obter_assinatura_sistema() or {}
    config = carregar_config()
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
    {_render_nav(cliente, admin_user)}
    <section class="hero">
      <div>
        <div class="eyebrow">CRM e Painel Administrativo</div>
        <h1>Visao central da operacao SaaS</h1>
        <p>Aqui voce enxerga clientes do portal, planos vendidos, assinatura do sistema, mensalidades e saude da base comercial.</p>
      </div>
      <div class="hero-side">
        <div class="meta-card"><div class="meta-label">Administrador</div><div class="meta-value">{escape(admin_user.get('nome', ''))}</div></div>
        <div class="meta-card"><div class="meta-label">Assinatura atual</div><div class="meta-value"><span class="badge {badge_tipo}">{escape(badge_texto)}</span></div></div>
        <div class="meta-card"><div class="meta-label">Plano vigente</div><div class="meta-value">{escape(assinatura.get('plano_nome') or 'Nao definido')}</div></div>
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
              <select name="plano_code">{''.join(f"<option value='{escape(plano['code'])}' {'selected' if plano['code'] == assinatura.get('plano_code') else ''}>{escape(plano['nome'])}</option>" for plano in listar_planos_cobranca(apenas_ativos=False))}</select>
            </label>
            <label>Status
              <select name="status">{''.join(f"<option value='{status}' {'selected' if status == (assinatura.get('status') or '').lower() else ''}>{_plan_badge(status)[0]}</option>" for status in ['development','trial','active','paid','blocked','suspended','cancelled'])}</select>
            </label>
            <label>Proximo vencimento<input type="datetime-local" name="next_due_at" value="{escape(_fmt_dt_local(assinatura.get('next_due_at')))}"></label>
            <label>Carencia ate<input type="datetime-local" name="grace_until" value="{escape(_fmt_dt_local(assinatura.get('grace_until')))}"></label>
          </div>
          <div class="actions">
            <button class="btn-primary" type="submit">Salvar assinatura</button>
            <button class="btn-soft" type="submit" formaction="/cobrancas/gerar">Gerar cobranca do mes</button>
          </div>
        </form>
      </article>
      <article class="card span-5">
        <h2 class="section-title">Integracoes e acessos</h2>
        <div class="api-box">GET /api/status
GET /api/assinatura
GET /api/cobrancas

Portal comercial:
{_base_url()}/

Admin:
{_base_url()}/admin</div>
      </article>
    </section>
    <section class="grid">
      <article class="card span-12">
        <div class="status-line">
          <div>
            <h2 class="section-title" style="margin:0;">Mercado Pago</h2>
            <p class="subtitle" style="margin:8px 0 0;">Credenciais separadas por ambiente para ativar checkout real com seguranca. Esse bloco fica restrito ao administrador do sistema.</p>
          </div>
          <span class="badge info">{escape('Sandbox' if str(config.get('mp_environment', 'sandbox')).lower() == 'sandbox' else 'Producao')}</span>
        </div>
        <form method="post" action="/integracoes/mercadopago/salvar">
          <div class="form-grid">
            <label>Ambiente ativo
              <select name="mp_environment">
                <option value="sandbox" {'selected' if str(config.get('mp_environment', 'sandbox')).lower() == 'sandbox' else ''}>Sandbox / Teste</option>
                <option value="production" {'selected' if str(config.get('mp_environment', 'sandbox')).lower() == 'production' else ''}>Producao</option>
              </select>
            </label>
            <div></div>
          </div>
          <div class="form-grid">
            <label>Public Key de teste<input type="text" name="mp_public_key_test" value="{escape(config.get('mp_public_key_test', ''))}" placeholder="TEST-..."></label>
            <label>Access Token de teste<input type="password" name="mp_access_token_test" value="{escape(config.get('mp_access_token_test', ''))}" placeholder="TEST-..."></label>
            <label>Public Key de producao<input type="text" name="mp_public_key_prod" value="{escape(config.get('mp_public_key_prod', ''))}" placeholder="APP_USR-..."></label>
            <label>Access Token de producao<input type="password" name="mp_access_token_prod" value="{escape(config.get('mp_access_token_prod', ''))}" placeholder="APP_USR-..."></label>
          </div>
          <div class="small">Use primeiro as credenciais de teste do Mercado Pago. Quando a validacao do checkout estiver pronta, troque o ambiente ativo para producao.</div>
          <div class="actions">
            <button class="btn-primary" type="submit">Salvar credenciais do Mercado Pago</button>
          </div>
        </form>
      </article>
    </section>
    <section class="grid">
      <article class="card span-6">
        <h2 class="section-title">Clientes e assinaturas</h2>
        <table>
          <thead><tr><th>Cliente</th><th>Plano</th><th>Status</th><th>Vencimento</th></tr></thead>
          <tbody>{''.join(linhas) or '<tr><td colspan="4">Nenhuma assinatura do portal encontrada.</td></tr>'}</tbody>
        </table>
      </article>
      <article class="card span-6">
        <h2 class="section-title">Mensalidades do sistema</h2>
        <table>
          <thead><tr><th>Competencia</th><th>Plano</th><th>Status</th><th>Valor</th></tr></thead>
          <tbody>{''.join(f"<tr><td>{int(c.get('referencia_mes',0)):02d}/{c.get('referencia_ano','')}</td><td>{escape(c.get('plano_nome') or c.get('plano_code') or '')}</td><td>{escape(_charge_badge(c.get('status'))[0])}</td><td>{escape(_fmt_money(c.get('valor', 0)))}</td></tr>" for c in cobrancas) or '<tr><td colspan=\"4\">Nenhuma cobranca do sistema encontrada.</td></tr>'}</tbody>
        </table>
      </article>
    </section>
    """
    return _layout(conteudo, titulo="Admin", mensagem=mensagem, erro=erro)


@app.on_event("startup")
def _startup():
    criar_banco()


@app.get("/", response_class=HTMLResponse)
def home(request: Request, msg: str = "", err: str = ""):
    return _html(_render_home(request, msg, err))


@app.get("/contratar")
def contratar(request: Request, plan: str = "", msg: str = "", err: str = ""):
    rendered = _render_choose_plan(request, plan, msg, err)
    return rendered if isinstance(rendered, RedirectResponse) else _html(rendered)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, plan: str = "", err: str = ""):
    return _html(_render_auth_page(request, "login", plan, err))


@app.get("/cadastro", response_class=HTMLResponse)
def cadastro_page(request: Request, plan: str = "", err: str = ""):
    return _html(_render_auth_page(request, "cadastro", plan, err))


@app.get("/checkout")
def checkout_page(request: Request, plan: str = "", err: str = ""):
    cliente = _cliente_logado(request)
    if not cliente:
        return _redirect("/login?err=" + urlencode({"": "Faca login para seguir."})[1:])
    return _html(_render_checkout(request, cliente, plan, err))


@app.get("/checkout/pix")
def checkout_pix_page(request: Request, id: str = "0", err: str = ""):
    cliente = _cliente_logado(request)
    if not cliente:
        return _redirect("/login?err=" + urlencode({"": "Faca login para seguir."})[1:])
    return _html(_render_pix_checkout(request, cliente, id, err))


@app.get("/checkout/cartao")
def checkout_cartao_page(request: Request, id: str = "0", err: str = ""):
    cliente = _cliente_logado(request)
    if not cliente:
        return _redirect("/login?err=" + urlencode({"": "Faca login para seguir."})[1:])
    return _html(_render_card_checkout(request, cliente, id, err))


@app.get("/checkout/retomar")
def checkout_retomar(request: Request, id: str = "0"):
    cliente = _cliente_logado(request)
    if not cliente:
        return _redirect("/login?err=" + urlencode({"": "Faca login para seguir."})[1:])
    checkout = obter_checkout_portal(id)
    if not checkout or int(checkout.get("cliente_id", 0)) != int(cliente["id"]):
        return _redirect("/portal?" + urlencode({"err": "Checkout pendente nao encontrado para este usuario."}))
    if _is_mercadopago_checkout(checkout):
        return _redirect("/checkout/mercadopago/continuar?" + urlencode({"id": checkout.get("id")}))
    metodo = str(checkout.get("payment_method") or "").strip().lower()
    if metodo == "cartao":
        return _redirect("/checkout/cartao?" + urlencode({"id": checkout.get("id")}))
    return _redirect("/checkout/pix?" + urlencode({"id": checkout.get("id")}))


@app.get("/portal", response_class=HTMLResponse)
def portal_page(request: Request, msg: str = "", err: str = ""):
    cliente = _cliente_logado(request)
    if not cliente:
        return _redirect("/login")
    return _html(_render_portal(request, cliente, msg, err))


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request, err: str = ""):
    if _admin_bootstrap_needed():
        return _redirect("/admin/bootstrap")
    admin = _require_admin(request)
    if admin:
        return _redirect("/admin")
    return _html(_render_admin_login(request, err))


@app.get("/admin/bootstrap", response_class=HTMLResponse)
def admin_bootstrap_page(request: Request, err: str = ""):
    if not _admin_bootstrap_needed():
        return _redirect("/admin/login")
    return _html(_render_admin_bootstrap(request, err))


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, msg: str = "", err: str = ""):
    if _admin_bootstrap_needed():
        return _redirect("/admin/bootstrap")
    admin = _require_admin(request)
    if not admin:
        return _redirect("/admin/login?err=" + urlencode({"": "Entre com um administrador para acessar o painel."})[1:])
    return _html(_render_admin(request, admin, msg, err))


@app.get("/logout")
def logout(request: Request):
    token = request.cookies.get("portal_session", "")
    if token:
        CLIENT_SESSIONS.pop(token, None)
    response = _redirect("/?msg=" + urlencode({"": "Sessao encerrada com sucesso."})[1:])
    _clear_cookie(response, "portal_session")
    return response


@app.get("/admin/logout")
def admin_logout(request: Request):
    token = request.cookies.get("portal_admin_session", "")
    if token:
        ADMIN_SESSIONS.pop(token, None)
    response = _redirect("/admin/login?err=" + urlencode({"": "Sessao administrativa encerrada."})[1:])
    _clear_cookie(response, "portal_admin_session")
    return response


@app.get("/api/status")
def api_status():
    return JSONResponse(avaliar_status_cobranca())


@app.get("/api/assinatura")
def api_assinatura():
    return JSONResponse(obter_assinatura_sistema() or {})


@app.get("/api/cobrancas")
def api_cobrancas():
    return JSONResponse(listar_cobrancas_mensais(limit=60))


@app.get("/healthz")
def healthcheck():
    return {"ok": True, "service": "billing_site", "framework": "fastapi"}


@app.post("/auth/login")
def auth_login(email: str = Form(""), password: str = Form(""), plan: str = Form("")):
    resultado = autenticar_cliente_portal(email, password)
    if not resultado.get("ok"):
        return _redirect("/login?" + urlencode({"plan": plan, "err": "Email ou senha invalidos."}))
    cliente = resultado["cliente"]
    token = secrets.token_urlsafe(24)
    CLIENT_SESSIONS[token] = cliente["id"]
    destino = "/checkout?" + urlencode({"plan": plan}) if plan else "/portal"
    response = _redirect(destino)
    _set_cookie(response, "portal_session", token)
    return response


@app.post("/auth/register")
def auth_register(
    nome: str = Form(""),
    email: str = Form(""),
    telefone: str = Form(""),
    documento: str = Form(""),
    endereco: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
    plan: str = Form(""),
):
    if password != password_confirm:
        return _redirect("/cadastro?" + urlencode({"plan": plan, "err": "As senhas nao conferem."}))
    cliente = criar_cliente_portal(
        nome=nome,
        email=email,
        password=password,
        telefone=telefone,
        documento=documento,
        endereco=endereco,
    )
    token = secrets.token_urlsafe(24)
    CLIENT_SESSIONS[token] = cliente["id"]
    destino = "/checkout?" + urlencode({"plan": plan}) if plan else "/portal"
    response = _redirect(destino)
    _set_cookie(response, "portal_session", token)
    return response


@app.post("/admin/login")
def admin_login(username: str = Form(""), password: str = Form("")):
    if _admin_bootstrap_needed():
        return _redirect("/admin/bootstrap")
    resultado = autenticar_usuario(username, password)
    if not resultado.get("ok"):
        return _redirect("/admin/login?" + urlencode({"err": "Credenciais administrativas invalidas ou acesso sem permissao."}))
    usuario = resultado.get("usuario") or {}
    if usuario.get("role") != "admin":
        return _redirect("/admin/login?" + urlencode({"err": "Somente administradores podem acessar este painel."}))
    token = secrets.token_urlsafe(24)
    ADMIN_SESSIONS[token] = usuario
    response = _redirect("/admin")
    _set_cookie(response, "portal_admin_session", token)
    return response


@app.post("/admin/testar-como-cliente")
def admin_testar_como_cliente(request: Request, plan: str = Form("")):
    admin = _require_admin(request)
    if not admin:
        return _redirect("/admin/login?err=" + urlencode({"err": "Entre como administrador para iniciar o teste."}))
    if _mercadopago_config()["environment"] != "sandbox":
        return _redirect("/login?" + urlencode({"plan": plan, "err": "Em producao, use um cliente real para testar a compra."}))
    cliente = _ensure_test_buyer()
    token = secrets.token_urlsafe(24)
    CLIENT_SESSIONS[token] = cliente["id"]
    destino = "/checkout?" + urlencode({"plan": plan}) if plan else "/portal"
    response = _redirect(destino)
    _set_cookie(response, "portal_session", token)
    return response


@app.post("/admin/bootstrap")
def admin_bootstrap(
    nome: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
):
    if not _admin_bootstrap_needed():
        return _redirect("/admin/login")
    if password != password_confirm:
        return _redirect("/admin/bootstrap?" + urlencode({"err": "As senhas nao conferem."}))
    try:
        criar_usuario(nome=nome, username=username, password=password, role="admin")
    except ValueError as exc:
        return _redirect("/admin/bootstrap?" + urlencode({"err": str(exc)}))
    return _redirect("/admin/login?" + urlencode({"err": "Administrador inicial criado. Entre com as novas credenciais."}))


@app.post("/checkout/iniciar")
def checkout_iniciar(request: Request, plan: str = Form(""), payment_method: str = Form("")):
    cliente = _cliente_logado(request)
    if not cliente:
        return _redirect("/login?err=" + urlencode({"": "Faca login para seguir."})[1:])
    checkout = iniciar_checkout_portal(
        cliente_id=cliente["id"],
        plano_code=plan,
        payment_method=payment_method,
    )
    if _mercadopago_ready():
        metodo = str(payment_method or "").strip().lower()
        try:
            checkout_mp = _mercadopago_criar_pagamento_unico(checkout) if metodo == "pix" else _mercadopago_criar_assinatura(checkout)
        except ValueError as exc:
            atualizar_checkout_portal_status(
                cobranca_id=checkout["id"],
                status="falhou",
                payment_method=payment_method,
                external_ref="mercadopago-checkout-error",
            )
            return _redirect("/checkout?" + urlencode({"plan": plan, "err": str(exc)}))
        external_id = str(checkout_mp.get("id") or "").strip()
        init_point = str(checkout_mp.get("init_point") or checkout_mp.get("sandbox_init_point") or "").strip()
        if not external_id or not init_point:
            atualizar_checkout_portal_status(
                cobranca_id=checkout["id"],
                status="falhou",
                payment_method=payment_method,
                external_ref="mercadopago-missing-init-point",
            )
            return _redirect("/checkout?" + urlencode({"plan": plan, "err": "O Mercado Pago nao retornou um link valido para o checkout."}))
        atualizar_checkout_portal_gateway(
            cobranca_id=checkout["id"],
            payment_method=payment_method,
            external_ref=external_id,
            gateway_checkout_url=init_point,
        )
        return RedirectResponse(url=init_point, status_code=303)
    rota = "/checkout/pix" if str(payment_method).strip().lower() == "pix" else "/checkout/cartao"
    return _redirect(rota + "?" + urlencode({"id": checkout["id"]}))


@app.get("/checkout/mercadopago/continuar")
def checkout_mercadopago_continuar(request: Request, id: str = "0"):
    cliente = _cliente_logado(request)
    if not cliente:
        return _redirect("/login?err=" + urlencode({"": "Faca login para seguir."})[1:])
    checkout = obter_checkout_portal(id)
    if not checkout or int(checkout.get("cliente_id", 0)) != int(cliente["id"]):
        return _redirect("/portal?" + urlencode({"err": "Checkout do Mercado Pago nao encontrado para este usuario."}))
    checkout_url = str(checkout.get("gateway_checkout_url") or "").strip()
    if not checkout_url:
        return _redirect("/portal?" + urlencode({"err": "Nao existe link salvo para continuar esse checkout do Mercado Pago."}))
    return RedirectResponse(url=checkout_url, status_code=303)


@app.get("/checkout/mercadopago/iniciar")
def checkout_mercadopago_iniciar(request: Request, id: str = "0"):
    cliente = _cliente_logado(request)
    if not cliente:
        return _redirect("/login?err=" + urlencode({"": "Faca login para seguir."})[1:])
    checkout = obter_checkout_portal(id)
    if not checkout or int(checkout.get("cliente_id", 0)) != int(cliente["id"]):
        return _redirect("/portal?" + urlencode({"err": "Checkout pendente nao encontrado para este usuario."}))
    if _is_mercadopago_checkout(checkout):
        return _redirect("/checkout/mercadopago/continuar?" + urlencode({"id": checkout.get("id")}))
    metodo = str(checkout.get("payment_method") or "").strip().lower()
    try:
        checkout_mp = _mercadopago_criar_pagamento_unico(checkout) if metodo == "pix" else _mercadopago_criar_assinatura(checkout)
    except ValueError as exc:
        return _redirect("/checkout/pix?" + urlencode({"id": checkout.get("id"), "err": str(exc)}))
    external_id = str(checkout_mp.get("id") or "").strip()
    init_point = str(checkout_mp.get("init_point") or checkout_mp.get("sandbox_init_point") or "").strip()
    if not external_id or not init_point:
        return _redirect("/checkout/pix?" + urlencode({"id": checkout.get("id"), "err": "O Mercado Pago nao retornou um link valido para o checkout."}))
    atualizar_checkout_portal_gateway(
        cobranca_id=checkout["id"],
        payment_method=checkout.get("payment_method") or "pix",
        external_ref=external_id,
        gateway_checkout_url=init_point,
    )
    return RedirectResponse(url=init_point, status_code=303)


@app.get("/checkout/mercadopago/verificar")
def checkout_mercadopago_verificar(request: Request, id: str = "0"):
    cliente = _cliente_logado(request)
    if not cliente:
        return _redirect("/login?err=" + urlencode({"": "Faca login para seguir."})[1:])
    checkout = obter_checkout_portal(id)
    if not checkout or int(checkout.get("cliente_id", 0)) != int(cliente["id"]):
        return _redirect("/portal?" + urlencode({"err": "Checkout do Mercado Pago nao encontrado para este usuario."}))
    return _redirect("/checkout/mercadopago/retorno?" + urlencode({"checkout_id": checkout.get("id")}))


@app.get("/checkout/mercadopago/retorno")
def checkout_mercadopago_retorno(
    checkout_id: str = "0",
    preapproval_id: str = "",
    id: str = "",
    payment_id: str = "",
    collection_id: str = "",
    collection_status: str = "",
    status: str = "",
):
    cobranca = obter_checkout_portal(checkout_id)
    if not cobranca:
        return _redirect("/portal?" + urlencode({"err": "Checkout do Mercado Pago nao encontrado."}))
    pagamento_externo = (payment_id or collection_id or "").strip()
    if pagamento_externo:
        try:
            pagamento_mp = _mercadopago_obter_pagamento(pagamento_externo)
        except ValueError as exc:
            return _redirect("/portal?" + urlencode({"err": str(exc)}))
        resultado_pagamento = _aplicar_pagamento_mercadopago(cobranca, pagamento_mp, collection_status or status)
        if resultado_pagamento == "aprovado":
            return _redirect("/portal?" + urlencode({"msg": "Pagamento confirmado pelo Mercado Pago e plano ativado com sucesso."}))
        if resultado_pagamento == "falhou":
            return _redirect("/portal?" + urlencode({"err": "Pagamento Mercado Pago nao aprovado."}))
        return _redirect("/portal?" + urlencode({"msg": f"Pagamento Mercado Pago com status {resultado_pagamento}. Aguarde a confirmacao."}))
    if str(cobranca.get("payment_method") or "").strip().lower() == "pix":
        try:
            pagamento_mp = _mercadopago_buscar_pagamento_por_referencia(str(cobranca.get("id")))
        except ValueError as exc:
            return _redirect("/portal?" + urlencode({"err": str(exc)}))
        if not pagamento_mp:
            return _redirect("/portal?" + urlencode({"msg": "Ainda nao encontramos o pagamento PIX no Mercado Pago. Aguarde alguns instantes e verifique novamente."}))
        resultado_pagamento = _aplicar_pagamento_mercadopago(cobranca, pagamento_mp)
        if resultado_pagamento == "aprovado":
            return _redirect("/portal?" + urlencode({"msg": "Pagamento confirmado pelo Mercado Pago e plano ativado com sucesso."}))
        if resultado_pagamento == "falhou":
            return _redirect("/portal?" + urlencode({"err": "Pagamento Mercado Pago nao aprovado."}))
        return _redirect("/portal?" + urlencode({"msg": f"Pagamento Mercado Pago com status {resultado_pagamento}. Aguarde a confirmacao."}))
    assinatura_externa = (preapproval_id or id or cobranca.get("external_ref") or "").strip()
    if not assinatura_externa:
        return _redirect("/portal?" + urlencode({"msg": "Retorno recebido. Consulte o status do pagamento no Mercado Pago para confirmar a ativacao."}))
    try:
        assinatura_mp = _mercadopago_obter_assinatura(assinatura_externa)
    except ValueError as exc:
        return _redirect("/portal?" + urlencode({"err": str(exc)}))
    mp_status = str(assinatura_mp.get("status") or status or "").strip().lower()
    if mp_status in {"authorized", "active"}:
        confirmar_pagamento_portal(cobranca_id=checkout_id, payment_method=cobranca.get("payment_method") or "mercadopago")
        return _redirect("/portal?" + urlencode({"msg": "Pagamento confirmado pelo Mercado Pago e plano ativado com sucesso."}))
    if mp_status in {"cancelled"}:
        atualizar_checkout_portal_status(
            cobranca_id=checkout_id,
            status="cancelado",
            payment_method=cobranca.get("payment_method") or "mercadopago",
            external_ref=assinatura_externa,
        )
        return _redirect("/portal?" + urlencode({"msg": "Checkout cancelado no Mercado Pago."}))
    atualizar_checkout_portal_status(
        cobranca_id=checkout_id,
        status="pendente",
        payment_method=cobranca.get("payment_method") or "mercadopago",
        external_ref=assinatura_externa,
    )
    return _redirect("/portal?" + urlencode({"msg": f"Checkout do Mercado Pago criado com status {mp_status or 'pendente'}. Aguarde a confirmacao do pagamento."}))


@app.post("/webhooks/mercadopago")
async def mercadopago_webhook(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    topic = str(request.query_params.get("topic") or request.query_params.get("type") or body.get("type") or "").strip()
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    pagamento_id = str(
        request.query_params.get("id")
        or request.query_params.get("data.id")
        or data.get("id")
        or body.get("id")
        or ""
    ).strip()
    if topic and topic not in {"payment", "payments"}:
        return JSONResponse({"ok": True, "ignored": topic})
    if not pagamento_id:
        return JSONResponse({"ok": True, "ignored": "missing_payment_id"})
    try:
        pagamento_mp = _mercadopago_obter_pagamento(pagamento_id)
    except ValueError as exc:
        MP_LOGGER.error("webhook_payment_error payment_id=%s error=%s", pagamento_id, exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=200)
    external_reference = str(pagamento_mp.get("external_reference") or "").strip()
    if not external_reference:
        return JSONResponse({"ok": True, "ignored": "missing_external_reference"})
    cobranca = obter_checkout_portal(external_reference)
    if not cobranca:
        return JSONResponse({"ok": True, "ignored": "checkout_not_found"})
    resultado = _aplicar_pagamento_mercadopago(cobranca, pagamento_mp)
    MP_LOGGER.info(
        "webhook_payment_applied payment_id=%s checkout_id=%s status=%s",
        pagamento_id,
        external_reference,
        resultado,
    )
    return JSONResponse({"ok": True, "status": resultado})


@app.post("/checkout/pix/aprovar")
def checkout_pix_aprovar(checkout_id: str = Form("0")):
    confirmar_pagamento_portal(cobranca_id=checkout_id, payment_method="pix")
    return _redirect("/portal?" + urlencode({"msg": "Pagamento PIX aprovado e plano ativado com sucesso."}))


@app.post("/checkout/cartao/processar")
def checkout_cartao_processar(
    checkout_id: str = Form("0"),
    card_name: str = Form(""),
    card_number: str = Form(""),
    card_expiry: str = Form(""),
    card_cvv: str = Form(""),
):
    numero = "".join(ch for ch in str(card_number) if ch.isdigit())
    if not numero or numero.endswith("0000"):
        atualizar_checkout_portal_status(
            cobranca_id=checkout_id,
            status="falhou",
            payment_method="cartao",
            external_ref="fastapi-card-declined",
        )
        return _redirect("/checkout/cartao?" + urlencode({"id": checkout_id, "err": "Pagamento nao autorizado. Revise os dados do cartao ou tente outra forma de pagamento."}))
    confirmar_pagamento_portal(cobranca_id=checkout_id, payment_method="cartao")
    return _redirect("/portal?" + urlencode({"msg": "Pagamento com cartao aprovado e plano ativado com sucesso."}))


@app.post("/checkout/cancelar")
def checkout_cancelar(checkout_id: str = Form("0")):
    atualizar_checkout_portal_status(cobranca_id=checkout_id, status="cancelado")
    return _redirect("/portal?" + urlencode({"msg": "Checkout cancelado."}))


@app.post("/assinatura/salvar")
def assinatura_salvar(
    request: Request,
    plano_code: str = Form(""),
    status: str = Form("active"),
    next_due_at: str = Form(""),
    grace_until: str = Form(""),
):
    if not _require_admin(request):
        return _redirect("/admin/login?err=" + urlencode({"": "Entre com um administrador para continuar."})[1:])
    salvar_assinatura_sistema(
        plano_code=plano_code,
        status=status,
        ciclo="mensal",
        next_due_at=next_due_at,
        grace_until=grace_until,
    )
    return _redirect("/admin?" + urlencode({"msg": "Assinatura do sistema atualizada."}))


@app.post("/cobrancas/gerar")
def cobrancas_gerar(request: Request):
    if not _require_admin(request):
        return _redirect("/admin/login?err=" + urlencode({"": "Entre com um administrador para continuar."})[1:])
    gerar_cobranca_mensal_atual()
    return _redirect("/admin?" + urlencode({"msg": "Cobranca do sistema gerada com sucesso."}))


@app.post("/cobrancas/status")
def cobrancas_status(
    request: Request,
    cobranca_id: str = Form("0"),
    status: str = Form("pendente"),
    payment_method: str = Form(""),
):
    if not _require_admin(request):
        return _redirect("/admin/login?err=" + urlencode({"": "Entre com um administrador para continuar."})[1:])
    atualizar_status_cobranca(
        cobranca_id=cobranca_id,
        status=status,
        payment_method=payment_method,
    )
    return _redirect("/admin?" + urlencode({"msg": "Status da cobranca atualizado."}))


@app.post("/integracoes/mercadopago/salvar")
def salvar_mercadopago(
    request: Request,
    mp_environment: str = Form("sandbox"),
    mp_public_key_test: str = Form(""),
    mp_access_token_test: str = Form(""),
    mp_public_key_prod: str = Form(""),
    mp_access_token_prod: str = Form(""),
):
    if not _require_admin(request):
        return _redirect("/admin/login?err=" + urlencode({"": "Entre com um administrador para continuar."})[1:])
    config = carregar_config()
    salvar_config(
        caminho_base=config.get("caminho_base", ""),
        login=config.get("login", ""),
        senha=config.get("senha", ""),
        recurrence_enabled=config.get("recurrence_enabled", False),
        recurrence_frequency=config.get("recurrence_frequency", "manual"),
        notification_email=config.get("notification_email", ""),
        smtp_sender_email=config.get("smtp_sender_email", ""),
        smtp_sender_password=config.get("smtp_sender_password", ""),
        mp_environment=mp_environment,
        mp_public_key_test=mp_public_key_test,
        mp_access_token_test=mp_access_token_test,
        mp_public_key_prod=mp_public_key_prod,
        mp_access_token_prod=mp_access_token_prod,
    )
    return _redirect("/admin?" + urlencode({"msg": "Credenciais do Mercado Pago salvas com sucesso."}))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "billing_site.app:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
