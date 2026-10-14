-- empties every application table of the local database before the import (migrations history kept)
set client_min_messages = warning;
do $$
declare
    name text;
begin
    for name in select tablename from pg_tables where schemaname = 'public' and tablename <> 'django_migrations' loop
        execute format('truncate table public.%I restart identity cascade', name);
    end loop;
end $$;
