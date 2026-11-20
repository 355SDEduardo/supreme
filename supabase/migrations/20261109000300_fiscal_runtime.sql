BEGIN;

CREATE TABLE IF NOT EXISTS companies.portfolio_resources (
	id VARCHAR(200) NOT NULL, 
	company_id VARCHAR(100) NOT NULL, 
	kind VARCHAR(30) NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	competence VARCHAR(7), 
	organization_id VARCHAR(100), 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS nfse.artifacts (
	organization_id VARCHAR(100) NOT NULL, 
	company_id VARCHAR(100) NOT NULL, 
	sha VARCHAR NOT NULL, 
	filename VARCHAR NOT NULL, 
	content VARCHAR NOT NULL, 
	PRIMARY KEY (organization_id, company_id, sha)
);

CREATE TABLE IF NOT EXISTS nfse.metadata (
	organization_id VARCHAR(100) NOT NULL, 
	company_id VARCHAR(100) NOT NULL, 
	key VARCHAR NOT NULL, 
	body JSONB NOT NULL, 
	PRIMARY KEY (organization_id, company_id, key)
);

CREATE TABLE IF NOT EXISTS nfse.outbox (
	organization_id VARCHAR(100) NOT NULL, 
	company_id VARCHAR(100) NOT NULL, 
	id VARCHAR NOT NULL, 
	body JSONB NOT NULL, 
	PRIMARY KEY (organization_id, company_id, id)
);

CREATE TABLE IF NOT EXISTS nfse.processed_notes (
	organization_id VARCHAR(100) NOT NULL, 
	company_id VARCHAR(100) NOT NULL, 
	key VARCHAR NOT NULL, 
	sha VARCHAR NOT NULL, 
	note JSONB NOT NULL, 
	canonical JSONB NOT NULL, 
	status VARCHAR NOT NULL, 
	PRIMARY KEY (organization_id, company_id, key)
);

CREATE TABLE IF NOT EXISTS nfse.snapshots (
	organization_id VARCHAR(100) NOT NULL, 
	company_id VARCHAR(100) NOT NULL, 
	version VARCHAR NOT NULL, 
	body JSONB NOT NULL, 
	PRIMARY KEY (organization_id, company_id, version)
);

CREATE TABLE IF NOT EXISTS nfse.tombstones (
	organization_id VARCHAR(100) NOT NULL, 
	company_id VARCHAR(100) NOT NULL, 
	key VARCHAR NOT NULL, 
	PRIMARY KEY (organization_id, company_id, key)
);

CREATE TABLE IF NOT EXISTS tax_audit.workspace_files (
	organization_id VARCHAR(100) NOT NULL, 
	company_id VARCHAR(100) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	reference VARCHAR(1000) NOT NULL, 
	PRIMARY KEY (organization_id, company_id, name)
);

CREATE INDEX IF NOT EXISTS ix_companies_portfolio_resources_company_id ON companies.portfolio_resources (company_id);

CREATE INDEX IF NOT EXISTS ix_companies_portfolio_resources_organization_id ON companies.portfolio_resources (organization_id);

REVOKE ALL ON TABLE companies.portfolio_resources FROM PUBLIC, anon, authenticated; GRANT SELECT, INSERT, UPDATE, DELETE ON companies.portfolio_resources TO supreme_companies; ALTER TABLE companies.portfolio_resources ENABLE ROW LEVEL SECURITY; DROP POLICY IF EXISTS supreme_backend ON companies.portfolio_resources; CREATE POLICY supreme_backend ON companies.portfolio_resources TO supreme_companies USING (true) WITH CHECK (true);

REVOKE ALL ON TABLE nfse.artifacts FROM PUBLIC, anon, authenticated; GRANT SELECT, INSERT, UPDATE, DELETE ON nfse.artifacts TO supreme_nfse; ALTER TABLE nfse.artifacts ENABLE ROW LEVEL SECURITY; DROP POLICY IF EXISTS supreme_backend ON nfse.artifacts; CREATE POLICY supreme_backend ON nfse.artifacts TO supreme_nfse USING (true) WITH CHECK (true);

REVOKE ALL ON TABLE nfse.metadata FROM PUBLIC, anon, authenticated; GRANT SELECT, INSERT, UPDATE, DELETE ON nfse.metadata TO supreme_nfse; ALTER TABLE nfse.metadata ENABLE ROW LEVEL SECURITY; DROP POLICY IF EXISTS supreme_backend ON nfse.metadata; CREATE POLICY supreme_backend ON nfse.metadata TO supreme_nfse USING (true) WITH CHECK (true);

REVOKE ALL ON TABLE nfse.outbox FROM PUBLIC, anon, authenticated; GRANT SELECT, INSERT, UPDATE, DELETE ON nfse.outbox TO supreme_nfse; ALTER TABLE nfse.outbox ENABLE ROW LEVEL SECURITY; DROP POLICY IF EXISTS supreme_backend ON nfse.outbox; CREATE POLICY supreme_backend ON nfse.outbox TO supreme_nfse USING (true) WITH CHECK (true);

REVOKE ALL ON TABLE nfse.processed_notes FROM PUBLIC, anon, authenticated; GRANT SELECT, INSERT, UPDATE, DELETE ON nfse.processed_notes TO supreme_nfse; ALTER TABLE nfse.processed_notes ENABLE ROW LEVEL SECURITY; DROP POLICY IF EXISTS supreme_backend ON nfse.processed_notes; CREATE POLICY supreme_backend ON nfse.processed_notes TO supreme_nfse USING (true) WITH CHECK (true);

REVOKE ALL ON TABLE nfse.snapshots FROM PUBLIC, anon, authenticated; GRANT SELECT, INSERT, UPDATE, DELETE ON nfse.snapshots TO supreme_nfse; ALTER TABLE nfse.snapshots ENABLE ROW LEVEL SECURITY; DROP POLICY IF EXISTS supreme_backend ON nfse.snapshots; CREATE POLICY supreme_backend ON nfse.snapshots TO supreme_nfse USING (true) WITH CHECK (true);

REVOKE ALL ON TABLE nfse.tombstones FROM PUBLIC, anon, authenticated; GRANT SELECT, INSERT, UPDATE, DELETE ON nfse.tombstones TO supreme_nfse; ALTER TABLE nfse.tombstones ENABLE ROW LEVEL SECURITY; DROP POLICY IF EXISTS supreme_backend ON nfse.tombstones; CREATE POLICY supreme_backend ON nfse.tombstones TO supreme_nfse USING (true) WITH CHECK (true);

REVOKE ALL ON TABLE tax_audit.workspace_files FROM PUBLIC, anon, authenticated; GRANT SELECT, INSERT, UPDATE, DELETE ON tax_audit.workspace_files TO supreme_tax_audit; ALTER TABLE tax_audit.workspace_files ENABLE ROW LEVEL SECURITY; DROP POLICY IF EXISTS supreme_backend ON tax_audit.workspace_files; CREATE POLICY supreme_backend ON tax_audit.workspace_files TO supreme_tax_audit USING (true) WITH CHECK (true);

COMMIT;
