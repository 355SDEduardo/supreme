-- Incremental. Not applied to a remote database by this repository.
BEGIN;

DO $$ BEGIN CREATE TYPE analytics.account_nature_enum AS ENUM ('debit', 'credit'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN CREATE TYPE analytics.account_type_enum AS ENUM ('asset', 'liability', 'equity', 'revenue', 'cogs', 'expense', 'financial'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN CREATE TYPE analytics.view_type_enum AS ENUM ('accrual_dre', 'cash_flow'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS analytics.chart_of_accounts (
	id VARCHAR(36) NOT NULL,
	company_id VARCHAR(36) NOT NULL,
	code VARCHAR(50) NOT NULL,
	name VARCHAR(255) NOT NULL,
	account_type analytics.account_type_enum NOT NULL,
	nature analytics.account_nature_enum NOT NULL,
	is_synthetic BOOLEAN,
	parent_id VARCHAR(36),
	organization_id VARCHAR(100),
	PRIMARY KEY (id),
	FOREIGN KEY(parent_id) REFERENCES analytics.chart_of_accounts (id)
);

CREATE INDEX IF NOT EXISTS ix_analytics_chart_of_accounts_company_id ON analytics.chart_of_accounts (company_id);

CREATE INDEX IF NOT EXISTS ix_analytics_chart_of_accounts_organization_id ON analytics.chart_of_accounts (organization_id);

CREATE TABLE IF NOT EXISTS analytics.cost_centers (
	id VARCHAR(36) NOT NULL,
	company_id VARCHAR(36) NOT NULL,
	code VARCHAR(50) NOT NULL,
	name VARCHAR(255) NOT NULL,
	organization_id VARCHAR(100),
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_analytics_cost_centers_company_id ON analytics.cost_centers (company_id);

CREATE INDEX IF NOT EXISTS ix_analytics_cost_centers_organization_id ON analytics.cost_centers (organization_id);

CREATE TABLE IF NOT EXISTS analytics.financial_snapshots (
	id VARCHAR(36) NOT NULL,
	company_id VARCHAR(36) NOT NULL,
	competence VARCHAR(7) NOT NULL,
	view_type analytics.view_type_enum NOT NULL,
	line_code VARCHAR(50) NOT NULL,
	line_description VARCHAR(255) NOT NULL,
	realized_amount NUMERIC(15, 2) NOT NULL,
	projected_amount NUMERIC(15, 2) NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	organization_id VARCHAR(100),
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_analytics_financial_snapshots_company_id ON analytics.financial_snapshots (company_id);

CREATE INDEX IF NOT EXISTS ix_analytics_financial_snapshots_competence ON analytics.financial_snapshots (competence);

CREATE INDEX IF NOT EXISTS ix_analytics_financial_snapshots_organization_id ON analytics.financial_snapshots (organization_id);

CREATE INDEX IF NOT EXISTS ix_analytics_financial_snapshots_view_type ON analytics.financial_snapshots (view_type);

REVOKE ALL ON TABLE analytics.chart_of_accounts FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE analytics.chart_of_accounts TO supreme_analytics;
ALTER TABLE analytics.chart_of_accounts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS supreme_backend ON analytics.chart_of_accounts;
CREATE POLICY supreme_backend ON analytics.chart_of_accounts TO supreme_analytics USING (true) WITH CHECK (true);

REVOKE ALL ON TABLE analytics.cost_centers FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE analytics.cost_centers TO supreme_analytics;
ALTER TABLE analytics.cost_centers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS supreme_backend ON analytics.cost_centers;
CREATE POLICY supreme_backend ON analytics.cost_centers TO supreme_analytics USING (true) WITH CHECK (true);

REVOKE ALL ON TABLE analytics.financial_snapshots FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE analytics.financial_snapshots TO supreme_analytics;
ALTER TABLE analytics.financial_snapshots ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS supreme_backend ON analytics.financial_snapshots;
CREATE POLICY supreme_backend ON analytics.financial_snapshots TO supreme_analytics USING (true) WITH CHECK (true);

COMMIT;
