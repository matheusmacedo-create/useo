-- Fixa o search_path da função de retenção (aviso 0011 do linter do Supabase)
-- e tira o EXECUTE de anon/authenticated: só a service key roda a limpeza.
-- O corpo da função já usa nomes qualificados (public.ai_runs).

alter function public.limpar_respostas_antigas(integer) set search_path = '';

revoke execute on function public.limpar_respostas_antigas(integer) from public;

-- anon/authenticated só existem no Supabase (o CI usa um Postgres puro).
do $$
declare
  papel text;
begin
  foreach papel in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = papel) then
      execute format(
        'revoke execute on function public.limpar_respostas_antigas(integer) from %I',
        papel);
    end if;
  end loop;
end
$$;
