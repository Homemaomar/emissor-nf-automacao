# Pacote De Deploy

Esta pasta concentra os arquivos para publicar o portal web em producao.

## Arquivos

- `systemd/mbs-portal.service`
  - sobe o portal `FastAPI/Uvicorn` como servico Linux

- `nginx/mbsduodigital.com.conf`
  - proxy reverso inicial para o dominio `mbsduodigital.com`

## Ajustes antes de usar

Edite os caminhos conforme o servidor:

- `WorkingDirectory`
- `EnvironmentFile`
- `ExecStart`

## Fluxo de publicacao

1. subir o projeto para `/var/www/mbsduodigital/emissor_nf`
2. criar `.venv`
3. instalar `requirements-web.txt`
4. copiar `.env.example` para `.env`
5. ajustar `BILLING_SITE_PUBLIC_URL=https://mbsduodigital.com`
6. copiar o arquivo `systemd/mbs-portal.service` para `/etc/systemd/system/`
7. copiar o arquivo `nginx/mbsduodigital.com.conf` para `/etc/nginx/sites-available/`
8. habilitar `nginx` e o servico
9. emitir SSL com `certbot`

## Comandos uteis no servidor

### systemd

```bash
sudo systemctl daemon-reload
sudo systemctl enable mbs-portal
sudo systemctl start mbs-portal
sudo systemctl status mbs-portal
```

### nginx

```bash
sudo ln -s /etc/nginx/sites-available/mbsduodigital.com.conf /etc/nginx/sites-enabled/mbsduodigital.com.conf
sudo nginx -t
sudo systemctl reload nginx
```

### SSL

```bash
sudo certbot --nginx -d mbsduodigital.com -d www.mbsduodigital.com
```
