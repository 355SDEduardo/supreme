-- Requires the storage extension managed by Supabase. No public object policies are installed.
BEGIN;
INSERT INTO storage.buckets (id, name, public, file_size_limit)
VALUES
  ('documents-custody', 'documents-custody', false, 52428800),
  ('nfse-xml', 'nfse-xml', false, 10485760),
  ('tax-audit-workspaces', 'tax-audit-workspaces', false, 52428800)
ON CONFLICT (id) DO UPDATE
SET public = false, file_size_limit = EXCLUDED.file_size_limit;
COMMIT;
