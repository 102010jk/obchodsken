-- Databáze potravin pro Supabase (Postgres). Odpovídá 1:1 formátu data/foods/FORMAT.md.

create table if not exists foods (
  id          text primary key check (id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  name        text not null check (length(trim(name)) > 0),
  brand       text,
  category    text not null check (category in ('OVOCE_ZELENINA','PECIVO','MASO_RYBY','UZENINY','MLECNE','VEJCE',
                'MRAZENE','TRVANLIVE','SLADKOSTI','NAPOJE','ALKOHOL','DROGERIE','ZVIRATA','OSTATNI')),
  size_value  numeric check (size_value > 0),
  size_unit   text check (size_unit in ('kg','l','ks')),
  image_url   text,
  sources     text[] not null default '{}',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  check ((size_value is null) = (size_unit is null))
);

-- Obchody, kde se potravina prodává – každý s vlastním názvem na účtence a odkazem.
create table if not exists food_stores (
  food_id             text not null references foods(id) on delete cascade,
  store               text not null,
  receipt_name        text,
  receipt_name_source text check (receipt_name_source in ('uctenka')),
  url                 text,
  primary key (food_id, store)
);
create index if not exists food_stores_receipt_name on food_stores (store, receipt_name);

create table if not exists food_eans (
  ean     text primary key check (ean ~ '^(\d{8}|\d{13})$'),
  food_id text not null references foods(id) on delete cascade
);

-- Příbuzné potraviny, ukládané oběma směry (A->B i B->A).
create table if not exists food_relations (
  food_id    text not null references foods(id) on delete cascade,
  related_id text not null references foods(id) on delete cascade,
  primary key (food_id, related_id),
  check (food_id <> related_id)
);

-- Čtení pro všechny, zápis jen přihlášení.
alter table foods enable row level security;
alter table food_stores enable row level security;
alter table food_eans enable row level security;
alter table food_relations enable row level security;
create policy "read foods" on foods for select using (true);
create policy "read food_stores" on food_stores for select using (true);
create policy "read food_eans" on food_eans for select using (true);
create policy "read food_relations" on food_relations for select using (true);
create policy "write foods" on foods for all to authenticated using (true) with check (true);
create policy "write food_stores" on food_stores for all to authenticated using (true) with check (true);
create policy "write food_eans" on food_eans for all to authenticated using (true) with check (true);
create policy "write food_relations" on food_relations for all to authenticated using (true) with check (true);
