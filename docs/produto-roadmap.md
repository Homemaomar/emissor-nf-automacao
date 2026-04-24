# Roadmap do produto

## Visao

Transformar o emissor em uma plataforma de operacao fiscal recorrente, com
experiencia mais premium, execucao previsivel e base pronta para escala.

## Fase 1 - Reposicionamento da experiencia

- Elevar a interface principal para um painel operacional mais claro.
- Destacar indicadores de lote, progresso e status da rotina.
- Organizar configuracoes para recorrencia, alertas e base de arquivos.
- Limpar textos tecnicos demais e reduzir cara de ferramenta interna.

## Fase 2 - Recorrencia real

- Salvar agenda de execucao diaria, semanal ou fechamento mensal.
- Criar status para "agendado", "em execucao", "falhou" e "reprocessado".
- Registrar historico por lote para auditoria e acompanhamento.
- Permitir alertas para falhas e conclusoes por email.

## Fase 3 - Escala operacional

- Tirar a planilha do centro da operacao e usar banco como fonte principal.
- Separar interface, orquestracao e workers de emissao/envio.
- Criar fila de execucao e reprocesso.
- Estruturar logs e observabilidade por empresa, municipio e periodo.

## Fase 4 - Produto premium

- Painel executivo com taxa de sucesso, SLA e valor processado.
- Caixa de pendencias com recomendacao de acao.
- Modelos de envio e historico por cliente.
- Base multiempresa com perfis, permissoes e trilha de auditoria.

## Proximas entregas sugeridas

1. Persistir agenda recorrente com horario e dia.
2. Remover credenciais hardcoded do fluxo de envio.
3. Criar historico de execucoes no banco.
4. Evoluir dashboard para mostrar falhas, fila e reprocesso.
