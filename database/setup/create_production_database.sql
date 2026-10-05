-- Production database on the server: the two roles and the 'attendance' database.
-- Run as the 'postgres' superuser by infrastructure/server/install.sh. The passwords come from
-- environment variables (\getenv), so they never appear in a command line. Safe to run again.
--
--   attendance_owner : owns the tables; used only by migrations and the nightly clean-up
--   attendance_app   : used by the running API; limited rights (granted by the migrations)

\set ON_ERROR_STOP on
\getenv owner_password DB_OWNER_PASSWORD
\getenv app_password DB_APP_PASSWORD

SELECT 'CREATE ROLE attendance_owner LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'attendance_owner') \gexec
SELECT 'CREATE ROLE attendance_app LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'attendance_app') \gexec

ALTER ROLE attendance_owner WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'owner_password';
ALTER ROLE attendance_app   WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';

SELECT 'CREATE DATABASE attendance OWNER attendance_owner TEMPLATE template0 ENCODING ''UTF8'' LOCALE_PROVIDER builtin BUILTIN_LOCALE ''C.UTF-8'' LOCALE ''C'''
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'attendance') \gexec

REVOKE ALL ON DATABASE attendance FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE attendance TO attendance_app;

\connect attendance
ALTER SCHEMA public OWNER TO attendance_owner;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

\echo 'Done: roles and database attendance are ready.'
