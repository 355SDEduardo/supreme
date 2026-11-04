#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --set=service_password="${DB_ACCOUNTING_AI_PASSWORD}" <<'SQL'
CREATE ROLE accounting_ai LOGIN PASSWORD :'service_password';
CREATE DATABASE accounting_ai OWNER accounting_ai;
REVOKE ALL ON DATABASE accounting_ai FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --set=service_password="${DB_ANALYTICS_DRE_PASSWORD}" <<'SQL'
CREATE ROLE analytics_dre LOGIN PASSWORD :'service_password';
CREATE DATABASE analytics_dre OWNER analytics_dre;
REVOKE ALL ON DATABASE analytics_dre FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --set=service_password="${DB_BANK_RECONCILIATION_PASSWORD}" <<'SQL'
CREATE ROLE bank_reconciliation LOGIN PASSWORD :'service_password';
CREATE DATABASE bank_reconciliation OWNER bank_reconciliation;
REVOKE ALL ON DATABASE bank_reconciliation FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --set=service_password="${DB_CLIENT_PORTAL_PASSWORD}" <<'SQL'
CREATE ROLE client_portal LOGIN PASSWORD :'service_password';
CREATE DATABASE client_portal OWNER client_portal;
REVOKE ALL ON DATABASE client_portal FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --set=service_password="${DB_COMPANIES_PASSWORD}" <<'SQL'
CREATE ROLE companies LOGIN PASSWORD :'service_password';
CREATE DATABASE companies OWNER companies;
REVOKE ALL ON DATABASE companies FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --set=service_password="${DB_DOCUMENTS_PASSWORD}" <<'SQL'
CREATE ROLE documents LOGIN PASSWORD :'service_password';
CREATE DATABASE documents OWNER documents;
REVOKE ALL ON DATABASE documents FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --set=service_password="${DB_FINANCE_BPO_PASSWORD}" <<'SQL'
CREATE ROLE finance_bpo LOGIN PASSWORD :'service_password';
CREATE DATABASE finance_bpo OWNER finance_bpo;
REVOKE ALL ON DATABASE finance_bpo FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --set=service_password="${DB_FISCAL_GOV_PASSWORD}" <<'SQL'
CREATE ROLE fiscal_gov LOGIN PASSWORD :'service_password';
CREATE DATABASE fiscal_gov OWNER fiscal_gov;
REVOKE ALL ON DATABASE fiscal_gov FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --set=service_password="${DB_OBLIGATIONS_PASSWORD}" <<'SQL'
CREATE ROLE obligations LOGIN PASSWORD :'service_password';
CREATE DATABASE obligations OWNER obligations;
REVOKE ALL ON DATABASE obligations FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --set=service_password="${DB_SECURITY_IAM_PASSWORD}" <<'SQL'
CREATE ROLE security_iam LOGIN PASSWORD :'service_password';
CREATE DATABASE security_iam OWNER security_iam;
REVOKE ALL ON DATABASE security_iam FROM PUBLIC;
SQL
