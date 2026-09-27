-- Read-only role for the deployed app. Run once, as the database owner, after restoring
-- the frozen dump:
--   psql "$OWNER_URL" -v pw="'<password>'" -f db/deploy/readonly_role.sql
-- The app refuses to start in production unless its role can only SELECT.

CREATE ROLE marginalis_app LOGIN PASSWORD :pw;
SELECT format('GRANT CONNECT ON DATABASE %I TO marginalis_app', current_database()) \gexec
GRANT USAGE ON SCHEMA public TO marginalis_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO marginalis_app;   -- tables and views
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER ROLE marginalis_app SET default_transaction_read_only = on;
