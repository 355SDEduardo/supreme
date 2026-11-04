"""One service inventory for development, gateway, CLI and deployment checks."""
SERVICES = [
    ('security-iam', 'security', 8001), ('companies', 'companies', 8002),
    ('obligations', 'obligations', 8003), ('documents', 'documents', 8004),
    ('pdf-tools', 'pdf', 8005), ('nfse-engine', 'nfse', 8006),
    ('nfe-difal', 'nfe', 8007), ('federal-tax-audit', 'tax-audit', 8008),
    ('bank-reconciliation', 'reconciliation', 8009), ('finance-bpo', 'bills', 8010),
    ('fiscal-gov', 'fiscal', 8011), ('client-portal', 'portal', 8012),
    ('analytics-dre', 'analytics', 8013), ('accounting-ai', 'ai', 8014),
]
