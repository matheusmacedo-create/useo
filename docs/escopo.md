# Useo — escopo do projeto

Sistema próprio de monitoramento SEO + visibilidade em IA, substituto do plano
Starter da Semrush · v0.1 · 06/11/2026. Transcrição do PDF de escopo; este
arquivo é a versão viva.

## 0. O que existe no fim

1. Um painel web onde eu abro e vejo 5 sites, cada um com posição das keywords, saúde técnica e presença nas IAs.
2. Toda madrugada o sistema coleta sozinho; eu não aperto nada.
3. Cada site tem até 100 keywords rastreadas no Google Brasil, com histórico desde o dia 1.
4. Cada site tem até 50 prompts rodados em 3 IAs, com registro de quem foi citado no meu lugar.
5. Cada site tem um audit técnico semanal com lista de erros priorizada.
6. Um servidor MCP me deixa perguntar ao Claude "como está o site X essa semana" e ele responde com o dado real.
7. Um relatório mensal em PDF por site sai com um clique, pronto pra mandar ao cliente.
8. Custo recorrente total abaixo de US$ 80/mês nos 5 sites.
9. Tudo em um repositório meu, documentado, sem dependência de SaaS que eu não controle além das APIs de dado.
10. Se amanhã eu quiser vender como produto, a base aguenta 50 sites sem reescrever.

## 1. Objetivo e fora de escopo

**Objetivo:** cobrir os ~60% do plano Starter da Semrush (US$ 165/mês) que são uso real, com dado próprio, custo variável baixo e acesso via MCP.

| Dentro | Fora (nesta versão) |
|---|---|
| Rank tracking diário, Google BR, desktop + mobile | Backlinks (exige índice da web — comprar depois se precisar) |
| Site audit técnico semanal | Pesquisa de keywords com volume (Keyword Planner numa fase 2) |
| AI visibility em ChatGPT, Gemini e Perplexity | Análise de concorrentes orgânicos (depende de base grande de keywords) |
| Servidor MCP lendo o banco | Bing, YouTube, Amazon |
| Painel web simples + relatório PDF mensal | Multiusuário, login de cliente, cobrança |

## 2. Módulos e entregáveis

| Módulo | O que faz | Entregável de "pronto" |
|---|---|---|
| M1 Base | Banco, schema, cron, config dos sites, secrets | Tabelas criadas no Supabase; GitHub Action roda às 3h e grava um registro de execução |
| M2 Rank tracking | Consulta SERP por keyword, grava posição, URL ranqueada, features da SERP | 100 kw de 1 site com 7 dias de histórico e gráfico de posição |
| M3 MCP | Expõe o banco como ferramentas: posições, variações, resumo semanal | Claude responde "quais keywords caíram essa semana no site X" com dado real |
| M4 AI visibility | Roda prompts nas 3 IAs, extrai menção/citação/posição/concorrente, calcula score | 50 prompts de 1 site rodando 3x/semana; tabela "quem aparece no meu lugar" |
| M5 Site audit | Crawler + Lighthouse: status, títulos, meta, canonical, links quebrados, Core Web Vitals | Audit semanal com lista priorizada (crítico / alerta / info) |
| M6 Painel + PDF | Interface web por site e relatório mensal | Painel no ar na Vercel; PDF gerado com 1 clique |

## 3. Arquitetura e stack

| Camada | Escolha | Por quê |
|---|---|---|
| Coletores | Python 3.12, scripts por módulo | Libs de scraping e APIs maduras |
| Banco | Supabase (Postgres) | Já em uso; grátis até 500 MB; API REST pronta pro painel |
| Agendamento | GitHub Actions (cron) | Grátis, sem servidor, log de cada execução |
| SERP | DataForSEO (SERP API) | Pay-per-use, sem proxy pra manter, Google BR + mobile |
| Crawler | Playwright + Lighthouse CI | Renderiza JS; Lighthouse dá CWV igual ao do Google |
| IAs | OpenAI (web search), Gemini (grounding), Perplexity Sonar | Os 3 com busca web na API |
| MCP | TypeScript, SDK oficial | Roda local no Claude Desktop/Code; 4–6 ferramentas |
| Painel | Next.js na Vercel | Já em uso; lê Supabase direto |
| Relatório PDF | HTML + Chrome headless | Mesmo template do painel vira PDF |

Fluxo: `cron → coletores Python → Supabase ← MCP / painel / PDF`. Nenhum serviço fica rodando 24h; só o banco.

## 4. Modelo de dados

Implementado em [`supabase/migrations/`](../supabase/migrations). Nomes de coluna sem acento.

| Tabela | Campos principais |
|---|---|
| `sites` | id, dominio, nome, marca[] (variações pra detecção), concorrentes[], ativo |
| `keywords` | id, site_id, termo, device, localizacao, tag, criado_em |
| `rank_checks` | keyword_id, data, posicao, url, serp_features[], top10_dominios[] |
| `prompts` | id, site_id, texto, categoria, ativo |
| `ai_runs` | prompt_id, data, modelo, resposta_raw, mencionou, citou_dominio, posicao, marcas_citadas[], fontes[], custo_usd |
| `audits` | id, site_id, data, paginas_rastreadas, score_lighthouse, resumo_json |
| `audit_issues` | audit_id, url, tipo, severidade, detalhe |
| `runs` | modulo, inicio, fim, status, erro, custo_usd — todo job grava aqui |

Regra: `ai_runs.resposta_raw` guarda a resposta inteira. Reprocessar o parser depois sem gastar API de novo é a maior economia do projeto.

## 5. Fontes externas e custo

| Item | Estimativa/mês |
|---|---|
| SERP · 500 kw/dia · DataForSEO | ~US$ 25 |
| IAs · 250 prompts × 3 modelos · 3x/semana | ~US$ 40 |
| Supabase, GitHub Actions, Vercel, crawler | US$ 0 |
| **Total nos 5 sites** | **~US$ 65** |

Valores estimados por tabela pública de nov/2026; confirmar na fase 1 com 1 site real antes de escalar. Se AI visibility rodar diário, dobra pra ~US$ 100.

| Fonte | Chave necessária | Limite que importa |
|---|---|---|
| DataForSEO | login + senha API, pré-pago | Mínimo de recarga US$ 50; ~US$ 0,002/SERP em fila |
| OpenAI | API key | Web search cobra por chamada além dos tokens |
| Google AI (Gemini) | API key | Grounding com cota gratuita diária pequena, depois pago |
| Perplexity | API key | Sonar é o mais barato dos 3 |
| Supabase | URL + service key | 500 MB grátis; `resposta_raw` é o que cresce — limpar após 180 dias |

## 6. Fases e ordem de construção

| Fase | Módulos | Esforço | Sai no fim |
|---|---|---|---|
| F1 | M1 Base + M2 Rank tracking | 1–2 dias | 1 site, 100 kw, cron rodando, custo real medido |
| F2 | M3 MCP | ½ dia | Já dá pra usar: Claude consulta posições |
| F3 | M4 AI visibility | 1 dia + lista de prompts | 1 site com 50 prompts, score semanal |
| F4 | M5 Site audit | 2 dias | Audit semanal com issues priorizadas |
| F5 | M6 Painel + PDF | 2–3 dias | Painel no ar, PDF mensal |
| F6 | Escalar pra 5 sites | ½ dia | Cadastro dos 4 restantes, revisão de custo |

Esforço = dias de trabalho com Claude Code, não dias corridos. Total: ~8–10 dias. Cada fase termina com algo usável; nunca duas fases abertas ao mesmo tempo.

**Primeiro site:** unicopag.com.br — tem marca, concorrentes claros (gateways/adquirentes) e o resultado interessa comercialmente.

## 7. Riscos

| Risco | Chance | Mitigação |
|---|---|---|
| AI visibility com variância alta; cliente lê ruído como resultado | Alta | Só mostrar média semanal; nunca valor de 1 rodada; aviso fixo no relatório |
| Custo de API foge do estimado | Média | `runs.custo_usd` em todo job + alerta se passar de US$ 5/dia |
| DataForSEO muda preço ou formato | Baixa | Coletor isolado numa função; trocar por SerpApi é 1 arquivo |
| Crawler derruba site do cliente ou é bloqueado | Média | Limite de 1 req/s, máx 500 páginas, user-agent identificado |
| Banco cresce com `resposta_raw` | Média | Retenção de 180 dias; comprimir texto |
| Projeto vira "só mais um painel" e ninguém olha | Alta | MCP antes do painel: se eu não usar via Claude, nem construir o painel |
| Esperar efeito em 1 mês | Alta | Horizonte combinado desde o início: diagnóstico mês 1, leitura real mês 4–6 |

## 8. Critérios de pronto (v1)

1. 5 sites cadastrados, 500 kw rastreadas, 30 dias seguidos de coleta sem falha manual.
2. 250 prompts rodando 3x/semana, parser com >95% de acerto numa amostra de 50 respostas revisadas à mão.
3. Audit semanal em todos os sites, nenhum crawl acima de 10 minutos.
4. MCP com 6 ferramentas: `posicoes`, `variacoes`, `ai_score`, `concorrentes_ia`, `issues`, `resumo_semana`.
5. PDF mensal gerado pros 5 sites e enviado a pelo menos 1 cliente real.
6. Custo do mês fechado abaixo de US$ 80 e registrado em `runs`.
7. README no repo que permite reinstalar do zero em 1 hora.

## 9. Decisões

Defaults do escopo aplicados enquanto não houver resposta diferente.

| # | Decisão | Valor em uso |
|---|---|---|
| 1 | Nome do projeto e do repo | `matheusmacedo-create/useo` (o escopo sugeria `matheusnsp/useo`; o repo criado foi este) |
| 2 | Quais 5 sites entram primeiro | unicopag.com.br; os outros 4 na F6 |
| 3 | AI visibility diário ou 3x/semana | 3x/semana |
| 4 | Painel público com login ou só local | Local na v1 |
| 5 | Quem paga as APIs | Conta pessoal, separada do CNPJ da Unicopag |
| 6 | Supabase: projeto novo ou existente | Projeto novo, isolado |
