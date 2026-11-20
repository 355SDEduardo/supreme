import { createRequire } from 'node:module';
const require = createRequire(new URL('../outputs/supabase-validation/package.json', import.meta.url));
const { PGlite } = require('@electric-sql/pglite');
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
process.on('uncaughtException', error => { console.error(error.message); process.exit(1); });

const db = new PGlite();
const migrations = [
  'supabase/migrations/20261109000100_supreme_domains.sql',
  'supabase/migrations/20261109000200_private_storage.sql',
  'supabase/migrations/20261109000300_fiscal_runtime.sql',
  'supabase/migrations/20261109000400_outbox_and_archive.sql',
  'supabase/migrations/20261109000500_analytics_models.sql',
];
async function apply() {
  for (const file of migrations) await db.exec(readFileSync(file, 'utf8'));
}
await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE SCHEMA storage; CREATE TABLE storage.buckets (id text PRIMARY KEY, name text, public boolean, file_size_limit bigint);');
await apply();
await db.exec("INSERT INTO events.events(event_id,kind,body) VALUES('synthetic-event','Example','{}');");
await apply();
assert.equal((await db.query('SELECT count(*)::int AS n FROM events.events')).rows[0].n, 1);
assert.equal((await db.query('SELECT count(*)::int AS n FROM storage.buckets WHERE NOT public')).rows[0].n, 3);
const schemas = ['iam','companies','obligations','documents','reconciliation','finance','fiscal_gov','portal','analytics','ai','nfse','nfe','tax_audit','events'];
for (const schema of schemas) {
  const tables = (await db.query('SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname=$1', [schema])).rows;
  assert(tables.length > 0);
  assert(tables.every(table => table.rowsecurity));
  const readable = tables.map(table => table.tablename).filter(name => name !== 'events_archive');
  assert(readable.length > 0);
  await db.exec(`SET ROLE supreme_${schema}`);
  await db.query(`SELECT * FROM ${schema}.${readable[0]} LIMIT 1`);
  await assert.rejects(db.query(`SELECT * FROM ${schema === 'iam' ? 'companies.companies' : 'iam.iam_users'}`), /permission denied/);
  await db.exec('RESET ROLE');
}
for (const role of ['anon', 'authenticated']) {
  await db.exec(`SET ROLE ${role}`);
  await assert.rejects(db.query('SELECT * FROM reconciliation.pluggy_configurations'), /permission denied/);
  await db.exec('RESET ROLE');
}
await db.exec("INSERT INTO iam.audit_logs(id,action,resource_type,ip_address,created_at) VALUES('synthetic','test','test','127.0.0.1',now());");
await assert.rejects(db.exec("DELETE FROM iam.audit_logs WHERE id='synthetic'"), /append-only/);
const required = [
  ['companies', 'portfolio_resources', 'organization_id'],
  ['nfse', 'artifacts', 'content'],
  ['nfse', 'processed_notes', 'canonical'],
  ['nfse', 'snapshots', 'body'],
  ['nfse', 'outbox', 'body'],
  ['nfe', 'fiscal_catalog', 'rule_payload'],
  ['nfe', 'processing_sessions', 'expires_at'],
  ['nfe', 'event_outbox', 'body'],
  ['tax_audit', 'audit_snapshots', 'snapshot_payload'],
  ['tax_audit', 'workspace_files', 'reference'],
  ['tax_audit', 'event_outbox', 'id'],
  ['events', 'events_archive', 'event_id'],
  ['analytics', 'chart_of_accounts', 'account_type'],
  ['analytics', 'cost_centers', 'code'],
  ['analytics', 'financial_snapshots', 'realized_amount'],
];
for (const [schema, table, column] of required) {
  const found = await db.query(
    'SELECT count(*)::int AS n FROM information_schema.columns WHERE table_schema=$1 AND table_name=$2 AND column_name=$3',
    [schema, table, column]);
  assert.equal(found.rows[0].n, 1, `${schema}.${table}.${column}`);
}
await db.exec('SET ROLE supreme_nfe');
await db.query('SELECT id FROM nfe.event_outbox LIMIT 1');
await db.exec('RESET ROLE');
await db.exec('SET ROLE supreme_events');
const maintenanceSource = readFileSync('scripts/supabase_maintenance.py', 'utf8');
const pendingSQL = maintenanceSource.match(/PENDING_EVENTS = """([\s\S]*?)"""/)[1];
const runtimeReport = (await db.query(pendingSQL)).rows[0];
assert.equal(Number(runtimeReport.total_events), 1);
assert.equal(Number(runtimeReport.without_delivery), 1);
await assert.rejects(db.exec("DELETE FROM events.events WHERE event_id='synthetic-event'"), /permission denied/);
await assert.rejects(db.query('SELECT event_id FROM events.events_archive'), /permission denied/);
await db.exec('RESET ROLE');
console.log('PASS: five migrations, repeat application, model columns, 14 service roles, RLS, browser isolation, private buckets, immutable audit and archive denial.');
await db.close();
