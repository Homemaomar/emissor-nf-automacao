# Deploy Do Portal Web

Este portal agora roda em `FastAPI + Uvicorn` pela entrada:

- `billing_site.app:app`

## 1. Dependencias

Instale as dependencias web:

```powershell
python -m pip install -r requirements-web.txt
```

## 2. Variaveis de ambiente

Copie `.env.example` para `.env` e ajuste os valores:

- `BILLING_SITE_HOST`
- `BILLING_SITE_PORT`
- `BILLING_SITE_PUBLIC_URL`
- `BILLING_SITE_SECURE_COOKIES`

Configuracao recomendada para producao:

```env
BILLING_SITE_HOST=0.0.0.0
BILLING_SITE_PORT=8765
BILLING_SITE_PUBLIC_URL=https://mbsduodigital.com
BILLING_SITE_SECURE_COOKIES=1
```

## 3. Inicializacao local

Opcao 1:

```powershell
python -m billing_site.app
```

Opcao 2:

```powershell
python -m uvicorn billing_site.app:app --host 0.0.0.0 --port 8765
```

## 4. Publicacao recomendada

Stack recomendada:

- `Ubuntu`
- `Python 3.14+`
- `Uvicorn`
- `Nginx`
- `Let's Encrypt`

Fluxo:

1. subir o projeto no servidor
2. criar ambiente virtual
3. instalar `requirements-web.txt`
4. configurar `.env`
5. subir `uvicorn`
6. colocar `Nginx` na frente com proxy reverso
7. emitir SSL com `Let's Encrypt`

Arquivos de apoio ja prontos no projeto:

- [deploy/README_DEPLOY.md](C:\AutomaçãoNotaFiscal\emissor_nf\deploy\README_DEPLOY.md)
- [deploy/systemd/mbs-portal.service](C:\AutomaçãoNotaFiscal\emissor_nf\deploy\systemd\mbs-portal.service)
- [deploy/nginx/mbsduodigital.com.conf](C:\AutomaçãoNotaFiscal\emissor_nf\deploy\nginx\mbsduodigital.com.conf)

## 5. Exemplo de comando com Uvicorn

```powershell
python -m uvicorn billing_site.app:app --host 127.0.0.1 --port 8765 --proxy-headers
```

## 6. Exemplo de proxy reverso Nginx

```nginx
server {
    server_name mbsduodigital.com www.mbsduodigital.com;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 6.1 DNS recomendado

Crie os apontamentos:

- `A` para `mbsduodigital.com`
- `A` para `www.mbsduodigital.com`

Ambos devem apontar para o IP publico do servidor.

## 7. O que ja esta pronto

- portal comercial
- cadastro e login de cliente
- checkout PIX e cartao em homologacao
- area do usuario
- CRM admin
- admin protegido por login do sistema
- endpoint de saude: `/healthz`

## 8. O que ainda falta antes da operacao comercial real

- gateway real de `PIX`
- gateway real de `cartao`
- webhooks de confirmacao
- banco de producao recomendado: `PostgreSQL`
- persistencia de sessoes fora da memoria
- endurecimento adicional de seguranca

## 9. Ordem sugerida para publicacao real

1. provisionar servidor Linux
2. apontar DNS do dominio
3. subir o portal com `systemd`
4. colocar `Nginx`
5. ativar SSL
6. validar login de cliente e login admin
7. migrar o banco web para `PostgreSQL`
8. integrar gateway real de `PIX` e `cartao`
