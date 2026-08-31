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
--   with dbname=polymarket, role=app-tradingcenter-polymarket-data;
--   with dbname=strategy,   role=app-tradingcenter-strategy;
--   and with dbname=social, role=app-tradingcenter-social-data.
--
-- The six databases are `agent`, `market_data`, `teams`, `polymarket`, `strategy` and
-- `social` (infra/database.tf). `tradingcenter` is the *server*, not a database on it, and asking
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
-- `social` is the same again, one change later (`social-data-collects-the-posts`): created
-- empty by that apply, owed the principal and then this script, and without them the module
-- starts, refuses on its first CREATE TABLE and the deploy probe says so.
--
-- `strategy` is the same again, one change earlier (`a-strategy-is-a-catalogue-entry`):
-- created empty by that apply, and owed both steps below — the principal first, then this
-- script — before the deploy that gives it an image. The module's lifespan migrates under
-- an advisory lock before it serves anything, so without them it starts, refuses, and the
-- deploy probe reports what the container actually did rather than what the control plane
-- thinks.
--
-- The password is an Entra access token:
--   az account get-access-token --resource https://ossrdbms-aad.database.windows.net \
--      --query accessToken -o tsv
--
-- **The role has to exist first, and creating it is a step of its own** — this script
-- grants to a role, it does not make one. `GRANT :"role" TO current_user` on the second
-- line below is what fails when it is missing, before anything is granted. Found on
-- 22 August 2026 while doing this for `polymarket`: the step had been performed three
-- times and written down nowhere.
--
--   -- against dbname=postgres, which is the only database carrying the extension.
--   -- Roles are cluster-wide, so it does not matter that the new database is elsewhere.
--   SELECT pgaadauth_create_principal_with_oid(
--            'app-tradingcenter-polymarket-data',      -- = the App Service's name
--            '<managed identity object id>',           -- terraform output …_principal_id
--            'service', false, false);
--
-- `_with_oid` and `'service'` rather than `pgaadauth_create_principal`: the caller is an
-- App Service's managed identity, not a person, and it is found by object id.
--
-- No psql on the machine is not a reason to install one:
--   docker run --rm -e PGPASSWORD="$TOKEN" -v "$PWD/scripts:/s:ro" postgres:17-alpine \
--     psql "host=… dbname=polymarket user='<admin upn>' sslmode=require" \
--     -v role=app-tradingcenter-polymarket-data -f /s/grant-schema-ownership.sql
--
-- The server's firewall admits `var.developer_ip_address` (infra/database.tf), which is
-- one address and is the operator's usual one. From anywhere else, add a rule for the
-- moment and take it away afterwards rather than moving that variable to whichever
-- network they happen to be on:
--   az postgres flexible-server firewall-rule create -g rg-tradingcenter \
--      -n psql-tradingcenter --rule-name TempOperatorGrant \
--      --start-ip-address <ip> --end-ip-address <ip>
--   … and `firewall-rule delete --rule-name TempOperatorGrant --yes` when done.
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
