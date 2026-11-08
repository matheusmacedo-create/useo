# Useo

Monitoramento SEO + visibilidade em IA, feito em casa pra substituir o plano
Starter da Semrush. Escopo completo em [`docs/escopo.md`](docs/escopo.md).

```
cron (GitHub Actions) → coletores Python → Supabase ← MCP / painel / PDF
```

## Estado

| Fase | Módulo | Estado |
|---|---|---|
| F1 | M1 Base: schema, cron, config, `runs` | ✅ código pronto, falta ligar as chaves |
| F1 | M2 Rank tracking (DataForSEO) | ✅ código pronto, falta ligar as chaves |
| F2 | M3 MCP | — |
| F3 | M4 AI visibility | — (tabelas já criadas) |
| F4 | M5 Site audit | — (tabelas já criadas) |
| F5 | M6 Painel + PDF | — |
| F6 | 5 sites | — |

## Estrutura

```
config/
  sites.yaml                 sites monitorados (fonte da verdade)
  keywords/<dominio>.csv     até 100 termos por site (termo,tag)
supabase/migrations/         schema completo (todas as tabelas do escopo)
collectors/                  pacote Python `useo` (CLI + coletores)
  useo/serp/dataforseo.py    único arquivo que conhece a DataForSEO
.github/workflows/
  nightly.yml                coleta às 03:07 de Brasília
  ci.yml                     testes + aplica o schema num Postgres limpo
docs/escopo.md               escopo, decisões e critérios de pronto
```

## Instalar do zero (~1 hora)

### 1. Supabase (projeto novo, isolado)

1. Crie um projeto em supabase.com (região São Paulo).
2. **SQL Editor** → cole e rode, em ordem, cada arquivo de `supabase/migrations/`.
   (Ou, com a CLI: `supabase link --project-ref <ref>` e `supabase db push`.)
3. **Project Settings → API**: anote a *Project URL* e a chave *service_role*.

Todas as tabelas têm RLS ligado e nenhuma policy: só a service key acessa.

### 2. DataForSEO

1. Conta em dataforseo.com, recarga mínima de US$ 50 (pré-pago).
2. **API Access**: anote o login e a senha *da API* (não é a senha do site).

### 3. Secrets no GitHub

Em **Settings → Secrets and variables → Actions → Secrets**:

| Nome | Valor |
|---|---|
| `SUPABASE_URL` | Project URL |
| `SUPABASE_SERVICE_KEY` | chave service_role |
| `DATAFORSEO_LOGIN` | login da API |
| `DATAFORSEO_PASSWORD` | senha da API |

Opcional em **Variables**: `USEO_COST_ALERT_USD` (padrão 5).

### 4. Keywords

Edite `config/keywords/unicopag.com.br.csv` (a lista atual é um rascunho) e,
se quiser, os concorrentes em `config/sites.yaml`. Cada termo vira uma
keyword por device listado em `devices`.

### 5. Primeira coleta (barata)

**Actions → coleta-noturna → Run workflow** com `limite = 4`. Depois confira no
Supabase:

```sql
select modulo, status, custo_usd, detalhe, erro from runs order by inicio desc;
```

Se o custo por consulta bateu com o esperado, rode de novo sem limite. A partir
daí o cron roda sozinho toda madrugada; rodar duas vezes no mesmo dia só
consulta o que faltou.

### Rodar local

```bash
cd collectors
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
cp ../.env.example ../.env   # preencha
python -m useo sync
python -m useo rank --limite 4
python -m useo chart --site unicopag.com.br --dias 30 --out saida/rank.html
pytest
```

## Comandos

| Comando | O que faz |
|---|---|
| `useo heartbeat` | grava um registro em `runs` (prova de vida do cron) |
| `useo sync` | copia `config/` pro banco; o que saiu da config vira `ativo = false` |
| `useo rank [--site D] [--limite N] [--data AAAA-MM-DD]` | coleta as posições do dia |
| `useo chart --site D [--dias 30]` | HTML com posição atual, variação 7d e histórico por keyword |
| `useo check-cost` | falha (e o GitHub manda e-mail) se o custo do dia passou do limite |

## Como o rank é calculado

- Uma consulta por keyword × device, Google Brasil (`location_code 2076`, `pt`), top 100.
- `posicao` = posição orgânica (`rank_group`) da **primeira** URL do domínio ou de
  um subdomínio; `null` = fora do top 100.
- `posicao_absoluta` conta todos os blocos da SERP (anúncios, PAA etc.).
- `serp_features` = tipos de bloco presentes além do orgânico.
- `top10_dominios` = os 10 primeiros orgânicos, em ordem (base pra concorrência).

Views prontas pro MCP/painel: `posicoes_atuais` (posição, dia anterior, 7 dias
atrás) e `custo_diario`.

## Custo

Todo job grava `custo_usd` em `runs`. O alerta de US$ 5/dia roda ao fim de cada
coleta. Atenção ao conferir a estimativa do escopo: com `devices: [desktop, mobile]`
cada termo custa 2 consultas por dia (100 termos = 200 SERPs/dia ≈ 6.000/mês por
site). Se o custo medido na F1 ficar alto, as alavancas são: só um device em
`config/sites.yaml`, `USEO_SERP_DEPTH` menor, ou menos termos.

## Trocar de provedor de SERP

`useo/serp/base.py` define o contrato (`SerpProvider.fetch` → `SerpBatch`).
Pra trocar DataForSEO por SerpApi, escreva `useo/serp/serpapi.py` com a mesma
interface e troque a linha que instancia o provedor em `useo/cli.py`.
