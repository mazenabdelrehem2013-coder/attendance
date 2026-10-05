-- Creates the two database roles and the dev + test databases.
-- Run as the 'postgres' superuser via infrastructure/local/setup-local-db.ps1
-- (it passes the passwords from backend/.env as psql variables). Safe to run again.
--
--   attendance_owner : owns the tables; used only by migrations and maintenance jobs
--   attendance_app   : used by the running API; gets limited rights (granted by migrations)

\set ON_ERROR_STOP on

SELECT 'CREATE ROLE attendance_owner LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'attendance_owner') \gexec
SELECT 'CREATE ROLE attendance_app LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'attendance_app') \gexec

ALTER ROLE attendance_owner WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'owner_password';
ALTER ROLE attendance_app   WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';

-- UTF-8 databases with a platform-independent locale (same behaviour on Windows and Cloud SQL).
SELECT 'CREATE DATABASE attendance_dev OWNER attendance_owner TEMPLATE template0 ENCODING ''UTF8'' LOCALE_PROVIDER builtin BUILTIN_LOCALE ''C.UTF-8'' LOCALE ''C'''
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'attendance_dev') \gexec
SELECT 'CREATE DATABASE attendance_test OWNER attendance_owner TEMPLATE template0 ENCODING ''UTF8'' LOCALE_PROVIDER builtin BUILTIN_LOCALE ''C.UTF-8'' LOCALE ''C'''
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'attendance_test') \gexec

REVOKE ALL ON DATABASE attendance_dev  FROM PUBLIC;
REVOKE ALL ON DATABASE attendance_test FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE attendance_dev  TO attendance_app;
GRANT CONNECT, TEMPORARY ON DATABASE attendance_test TO attendance_app;

-- The owner role must own the 'public' schema in each database so migrations can manage it.
\connect attendance_dev
ALTER SCHEMA public OWNER TO attendance_owner;
\connect attendance_test
ALTER SCHEMA public OWNER TO attendance_owner;

\echo 'Done: roles attendance_owner/attendance_app and databases attendance_dev/attendance_test are ready.'
