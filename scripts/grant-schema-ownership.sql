-- Hands a production database over to the role that will migrate it from now on.
--
-- Run once per database, as the server's Entra administrator, BEFORE deploying a module
-- that migrates itself. Modules apply their own migrations at startup with their own
-- identity (CLAUDE.md, "Migrations are never the operator's job"), and ALTER TABLE from
-- a role that does not own the table is refused — so a module deployed onto a database
-- that has not had this done will not start.
--
-- Why ownership rather than another round of GRANT: a grant covers the objects that
-- exist on the day it runs, and ALTER DEFAULT PRIVILEGES only covers what one named role
-- creates afterwards. Both were in place here and both were the wrong shape — the app
-- role could read every table the administrator had made and could alter none of them.
-- Once the app role owns what it created, neither is needed for anything it makes later.
--
-- Usage, from a machine whose IP the server's firewall admits:
--
--   psql "host=psql-tradingcenter.postgres.database.azure.com port=5432 dbname=agent \
--         user=<entra-admin-upn> sslmode=require" \
--        -v role=app-tradingcenter-agent -f scripts/grant-schema-ownership.sql
--
--   ... and again with dbname=market_data, role=app-tradingcenter-market-data;
--   with dbname=teams,      role=app-tradingcenter-agent — the *same* role as `agent`,
--                           because one App Service presents one identity since the two
--                           modules became the workbench;
--   and with dbname=polymarket, role=app-tradingcenter-polymarket-data.
--
-- The four databases are `agent`, `market_data`, `teams` and `polymarket`
-- (infra/database.tf). `tradingcenter` is the *server*, not a database on it, and asking
-- for it by that name is a FATAL.
--
-- **A brand-new, empty database still needs this.** Terraform creates it owned by the
-- administrator, and `CREATE ON SCHEMA public` has not been granted to PUBLIC since
-- PostgreSQL 15 — so a module deployed onto an untouched database fails on its first
-- `CREATE TABLE`, at startup, before it serves anything. Nothing here needs the database
-- to have objects in it; the loop below simply finds none.
--
-- `teams` has had this done — checked on 16 August 2026, before its first deployment:
-- `nspacl` on `public` carries the same shape `agent` has, and the database holds no
-- tables to reassign. Nothing is owed before that module ships.
--
-- `polymarket` has NOT. It is created empty by the apply that adds the module, and this
-- script against it is the one operator step that change carries — before the first
-- deploy, or polymarket-data starts, tries to migrate and stops.
--
-- The password is an Entra access token:
--   az account get-access-token --resource https://ossrdbms-aad.database.windows.net \
--      --query accessToken -o tsv
--
-- Idempotent: an object already owned by the role is reassigned to itself.

\set ON_ERROR_STOP on

-- The role name reaches the DO block below as a session setting, because a psql variable
-- does not survive into a PL/pgSQL body. Set outside the transaction so the check at the
-- bottom, which runs after COMMIT, still sees it.
SET my.target_role = :'role';

BEGIN;

-- Postgres refuses ALTER ... OWNER TO a role the current user is not a member of, and
-- Azure Flexible Server gives its Entra administrator no superuser to skip that with.
-- Membership is the whole of what is needed, and it is not a privilege the app role
-- gains — it is the administrator gaining the app role, which it already outranks.
GRANT :"role" TO current_user;

-- CREATE on `public` stopped being granted to PUBLIC in PostgreSQL 15, so a role that
-- owns every existing table still cannot add the next one without this.
GRANT CREATE, USAGE ON SCHEMA public TO :"role";

-- Tables, sequences and views, one loop rather than a list written out by hand: a list
-- is what leaves the object nobody remembered, and that object surfaces as a migration
-- failing months later. `alembic_version` is included by being a table like any other —
-- it is also the one that would fail first.
DO $$
DECLARE
    target text := current_setting('my.target_role');
    obj record;
BEGIN
    FOR obj IN
        SELECT c.relname AS name,
               CASE c.relkind
                   WHEN 'r' THEN 'TABLE'
                   WHEN 'p' THEN 'TABLE'
                   WHEN 'S' THEN 'SEQUENCE'
                   WHEN 'v' THEN 'VIEW'
                   WHEN 'm' THEN 'MATERIALIZED VIEW'
               END AS kind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind IN ('r', 'p', 'S', 'v', 'm')
          -- A sequence tied to a column follows its table and cannot be reassigned on
          -- its own — Postgres refuses with "cannot change owner of sequence ... is
          -- linked to table ...". Both link kinds have to be excluded: `a` is what a
          -- `serial` column produces, `i` what an identity column does. Filtering on
          -- `a` alone passes over the identity case, which is what `prompt_revisions`
          -- uses and what stopped the first run of this script.
          AND NOT EXISTS (
              SELECT 1 FROM pg_depend d
              WHERE d.classid = 'pg_class'::regclass
                AND d.objid = c.oid
                AND d.deptype IN ('a', 'i')
          )
    LOOP
        EXECUTE format('ALTER %s public.%I OWNER TO %I', obj.kind, obj.name, target);
    END LOOP;
END
$$;

COMMIT;

-- The check. Zero rows, or the transfer did not cover everything and the next migration
-- touching what is listed here will be refused.
SELECT c.relkind, c.relname, pg_get_userbyid(c.relowner) AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p', 'S', 'v', 'm')
  AND pg_get_userbyid(c.relowner) <> current_setting('my.target_role')
ORDER BY c.relname;
