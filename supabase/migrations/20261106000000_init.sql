-- Useo — schema inicial (M1 Base)
-- Cria todas as tabelas do modelo de dados (bloco 4 do escopo), mesmo as dos
-- módulos que ainda não existem, para que cada fase só acrescente código.
--
-- Acesso: os coletores e o MCP usam a service key (ignora RLS). RLS fica ligado
-- sem nenhuma policy, então a chave anon não lê nada até o painel (M6) definir
-- as suas.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- sites
-- ---------------------------------------------------------------------------
create table public.sites (
  id            uuid primary key default gen_random_uuid(),
  dominio       text not null unique,          -- sem www e sem protocolo: unicopag.com.br
  nome          text not null,
  marca         text[] not null default '{}',  -- variações do nome pra detecção em respostas de IA
  concorrentes  text[] not null default '{}',  -- domínios concorrentes
  ativo         boolean not null default true,
  criado_em     timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- keywords (uma linha por termo × device × localização)
-- ---------------------------------------------------------------------------
create table public.keywords (
  id            uuid primary key default gen_random_uuid(),
  site_id       uuid not null references public.sites(id) on delete cascade,
  termo         text not null,
  device        text not null default 'desktop' check (device in ('desktop', 'mobile')),
  localizacao   integer not null default 2076,  -- location_code do Google/DataForSEO; 2076 = Brasil
  idioma        text not null default 'pt',
  tag           text,
  ativo         boolean not null default true,
  criado_em     timestamptz not null default now(),
  unique (site_id, termo, device, localizacao)
);
create index keywords_site_idx on public.keywords (site_id) where ativo;

-- ---------------------------------------------------------------------------
-- rank_checks (uma linha por keyword por dia)
-- ---------------------------------------------------------------------------
create table public.rank_checks (
  id                 bigint generated always as identity primary key,
  keyword_id         uuid not null references public.keywords(id) on delete cascade,
  data               date not null,
  posicao            integer,           -- posição orgânica (rank_group); null = fora do top N
  posicao_absoluta   integer,           -- posição contando todos os blocos da SERP
  url                text,              -- URL do site que ranqueou
  serp_features      text[] not null default '{}',
  top10_dominios     text[] not null default '{}',
  coletado_em        timestamptz not null default now(),
  unique (keyword_id, data)
);
create index rank_checks_data_idx on public.rank_checks (data);

-- ---------------------------------------------------------------------------
-- prompts / ai_runs (M4)
-- ---------------------------------------------------------------------------
create table public.prompts (
  id         uuid primary key default gen_random_uuid(),
  site_id    uuid not null references public.sites(id) on delete cascade,
  texto      text not null,
  categoria  text,
  ativo      boolean not null default true,
  criado_em  timestamptz not null default now(),
  unique (site_id, texto)
);

create table public.ai_runs (
  id               bigint generated always as identity primary key,
  prompt_id        uuid not null references public.prompts(id) on delete cascade,
  data             date not null,
  modelo           text not null,
  resposta_raw     text,               -- resposta inteira: permite reprocessar o parser sem pagar a API de novo
  mencionou        boolean,
  citou_dominio    boolean,
  posicao          integer,
  marcas_citadas   text[] not null default '{}',
  fontes           text[] not null default '{}',
  custo_usd        numeric(10, 6) not null default 0,
  criado_em        timestamptz not null default now()
);
create index ai_runs_prompt_data_idx on public.ai_runs (prompt_id, data);

-- ---------------------------------------------------------------------------
-- audits / audit_issues (M5)
-- ---------------------------------------------------------------------------
create table public.audits (
  id                  uuid primary key default gen_random_uuid(),
  site_id             uuid not null references public.sites(id) on delete cascade,
  data                date not null,
  paginas_rastreadas  integer not null default 0,
  score_lighthouse    numeric(5, 2),
  resumo_json         jsonb not null default '{}'::jsonb,
  criado_em           timestamptz not null default now()
);
create index audits_site_data_idx on public.audits (site_id, data desc);

create table public.audit_issues (
  id          bigint generated always as identity primary key,
  audit_id    uuid not null references public.audits(id) on delete cascade,
  url         text not null,
  tipo        text not null,
  severidade  text not null check (severidade in ('critico', 'alerta', 'info')),
  detalhe     text
);
create index audit_issues_audit_idx on public.audit_issues (audit_id);

-- ---------------------------------------------------------------------------
-- runs — todo job grava aqui (início, fim, status, erro, custo)
-- ---------------------------------------------------------------------------
create table public.runs (
  id          bigint generated always as identity primary key,
  modulo      text not null,
  inicio      timestamptz not null default now(),
  fim         timestamptz,
  status      text not null default 'rodando' check (status in ('rodando', 'ok', 'parcial', 'erro')),
  erro        text,
  custo_usd   numeric(10, 6) not null default 0,
  detalhe     jsonb not null default '{}'::jsonb
);
create index runs_inicio_idx on public.runs (inicio desc);

-- ---------------------------------------------------------------------------
-- Views de leitura (usadas pelo CLI hoje; pelo MCP e painel depois)
-- ---------------------------------------------------------------------------

-- Custo por dia (fuso de Brasília), base do alerta de US$ 5/dia.
create view public.custo_diario as
select (inicio at time zone 'America/Sao_Paulo')::date as dia,
       modulo,
       sum(custo_usd) as custo_usd,
       count(*)       as execucoes
from public.runs
group by 1, 2;

-- Última posição de cada keyword, com a do dia anterior coletado e a de 7 dias antes.
create view public.posicoes_atuais as
with ult as (
  select distinct on (rc.keyword_id) rc.*
  from public.rank_checks rc
  order by rc.keyword_id, rc.data desc
)
select k.site_id,
       s.dominio,
       k.id as keyword_id,
       k.termo,
       k.device,
       k.tag,
       ult.data,
       ult.posicao,
       ult.url,
       ult.serp_features,
       (select r.posicao from public.rank_checks r
         where r.keyword_id = k.id and r.data < ult.data
         order by r.data desc limit 1)                                as posicao_anterior,
       (select r.posicao from public.rank_checks r
         where r.keyword_id = k.id and r.data <= ult.data - 7
         order by r.data desc limit 1)                                as posicao_7d
from public.keywords k
join public.sites s on s.id = k.site_id
join ult on ult.keyword_id = k.id
where k.ativo and s.ativo;

-- Views herdam o dono; com security_invoker respeitam o RLS de quem consulta.
alter view public.custo_diario set (security_invoker = on);
alter view public.posicoes_atuais set (security_invoker = on);

-- ---------------------------------------------------------------------------
-- Retenção: resposta_raw é o que faz o banco crescer. Apaga o texto bruto
-- depois de 180 dias, mantendo as colunas já extraídas.
-- ---------------------------------------------------------------------------
create function public.limpar_respostas_antigas(dias integer default 180)
returns integer
language sql
as $$
  with upd as (
    update public.ai_runs
       set resposta_raw = null
     where resposta_raw is not null
       and data < current_date - dias
    returning 1
  )
  select count(*)::integer from upd;
$$;

-- ---------------------------------------------------------------------------
-- RLS: ligado em tudo, sem policies (só a service key lê/escreve por ora).
-- ---------------------------------------------------------------------------
alter table public.sites         enable row level security;
alter table public.keywords      enable row level security;
alter table public.rank_checks   enable row level security;
alter table public.prompts       enable row level security;
alter table public.ai_runs       enable row level security;
alter table public.audits        enable row level security;
alter table public.audit_issues  enable row level security;
alter table public.runs          enable row level security;
