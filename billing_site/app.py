import os
import secrets
from html import escape
from urllib.parse import urlencode

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
    atualizar_status_cobranca,
    autenticar_cliente_portal,
    autenticar_usuario,
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


APP_HOST = os.environ.get("BILLING_SITE_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("BILLING_SITE_PORT", "8765"))
PUBLIC_BASE_URL = os.environ.get("BILLING_SITE_PUBLIC_URL", f"http://{APP_HOST}:{APP_PORT}")
SECURE_COOKIES = os.environ.get("BILLING_SITE_SECURE_COOKIES", "0").strip() in {"1", "true", "True"}

CLIENT_SESSIONS = {}
ADMIN_SESSIONS = {}

app = FastAPI(title="MBS Fiscal Portal", docs_url=None, redoc_url=None)


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


def _render_nav(cliente=None, admin=None):
    if admin:
        admin_links = '<a href="/admin" class="primary">Admin</a><a href="/admin/logout">Sair do admin</a>'
    else:
        admin_links = '<a href="/admin/login">Admin</a>'
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
    if modo == "login":
        form = f"""
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
    conteudo = f"""
    {_render_nav(cliente, admin)}
    <section class="grid">
      <article class="card span-7">
        <div class="badge info">Plano escolhido</div>
        <h1 style="font-size:34px;margin:12px 0 10px;">{escape(plano.get('nome', 'Plano'))}</h1>
        <p class="subtitle">Antes de seguir para o pagamento, o cliente pode entrar com a conta existente ou concluir um novo cadastro em poucos passos.</p>
        <div class="actions">
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
    conteudo = f"""
    {_render_nav(cliente, admin)}
    <section class="grid">
      <article class="card span-7">
        <h1 style="font-size:34px;margin-bottom:10px;">Checkout do plano</h1>
        <p class="subtitle">Escolha a forma de pagamento e siga para a etapa correspondente. O fluxo ja esta organizado para PIX e cartao em jornadas separadas.</p>
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
        <div class="meta-card" style="margin-top:12px;"><div class="meta-label">Mensalidade</div><div class="meta-value">{escape(_fmt_money(plano.get('valor_mensal', 0)))}</div></div>
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
        <div class="meta-card" style="margin-top:12px;"><div class="meta-label">Vencimento</div><div class="meta-value">{escape(checkout.get('due_at') or '-')}</div></div>
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
    badge_texto, badge_tipo = _plan_badge(assinatura.get("status") if assinatura else "checkout")
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
          <div class="small">Proximo vencimento: {escape(assinatura.get('next_due_at') or 'Ainda nao definido')}</div>
          <ul>{recursos}</ul>
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


def _render_admin(request: Request, admin_user, mensagem="", erro=""):
    cliente = _cliente_logado(request)
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


@app.get("/portal", response_class=HTMLResponse)
def portal_page(request: Request, msg: str = "", err: str = ""):
    cliente = _cliente_logado(request)
    if not cliente:
        return _redirect("/login")
    return _html(_render_portal(request, cliente, msg, err))


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request, err: str = ""):
    admin = _require_admin(request)
    if admin:
        return _redirect("/admin")
    return _html(_render_admin_login(request, err))


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, msg: str = "", err: str = ""):
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
    rota = "/checkout/pix" if str(payment_method).strip().lower() == "pix" else "/checkout/cartao"
    return _redirect(rota + "?" + urlencode({"id": checkout["id"]}))


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
