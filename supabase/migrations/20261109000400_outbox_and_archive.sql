-- Incremental. Not applied to a remote database by this repository.
-- Runtime roles keep their current privileges. events_archive is reserved for the database owner.
BEGIN;

CREATE TABLE IF NOT EXISTS nfe.event_outbox (
	organization_id VARCHAR(100) NOT NULL,
	company_id VARCHAR(100) NOT NULL,
	id VARCHAR(100) NOT NULL,
	body JSONB NOT NULL,
	PRIMARY KEY (organization_id, company_id, id)
);

CREATE TABLE IF NOT EXISTS tax_audit.event_outbox (
	organization_id VARCHAR(100) NOT NULL,
	company_id VARCHAR(100) NOT NULL,
	id VARCHAR(100) NOT NULL,
	body JSONB NOT NULL,
	PRIMARY KEY (organization_id, company_id, id)
);

CREATE TABLE IF NOT EXISTS events.events_archive (
	id BIGINT NOT NULL,
	event_id VARCHAR(100) NOT NULL,
	kind VARCHAR(100) NOT NULL,
	body JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	archived_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (event_id)
);

REVOKE ALL ON TABLE nfe.event_outbox FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE nfe.event_outbox TO supreme_nfe;
ALTER TABLE nfe.event_outbox ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS supreme_backend ON nfe.event_outbox;
CREATE POLICY supreme_backend ON nfe.event_outbox TO supreme_nfe USING (true) WITH CHECK (true);

REVOKE ALL ON TABLE tax_audit.event_outbox FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE tax_audit.event_outbox TO supreme_tax_audit;
ALTER TABLE tax_audit.event_outbox ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS supreme_backend ON tax_audit.event_outbox;
CREATE POLICY supreme_backend ON tax_audit.event_outbox TO supreme_tax_audit USING (true) WITH CHECK (true);

REVOKE ALL ON TABLE events.events_archive FROM PUBLIC, anon, authenticated, supreme_events;
ALTER TABLE events.events_archive ENABLE ROW LEVEL SECURITY;

COMMIT;
