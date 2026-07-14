-- TrackGuard Demo Seed Data
-- Run: psql "$DATABASE_URL" -f scripts/seed_data.sql

-- Seed demo tenant
INSERT INTO founders (tenant_id, telegram_chat_id, name, stage)
VALUES ('demo-tenant-001', '42', 'Demo Founder', 'prerevenue')
ON CONFLICT (tenant_id) DO NOTHING;

-- Seed vendor baselines
INSERT INTO vendor_baselines (tenant_id, vendor_name, avg_30d, avg_90d, transaction_count)
VALUES 
    ('demo-tenant-001', 'AWS', 18000.00, 18000.00, 12),
    ('demo-tenant-001', 'Vercel', 5000.00, 5000.00, 12),
    ('demo-tenant-001', 'Slack', 2000.00, 2000.00, 12),
    ('demo-tenant-001', 'Notion', 800.00, 800.00, 12)
ON CONFLICT (tenant_id, vendor_name) DO NOTHING;

-- Seed finance snapshots
INSERT INTO finance_snapshots (tenant_id, snapshot_date, monthly_revenue, monthly_expense, burn_rate, runway_months)
VALUES 
    ('demo-tenant-001', CURRENT_DATE, 200000.00, 80000.00, 80000.00, 6.25)
ON CONFLICT (tenant_id, snapshot_date) DO NOTHING;

-- Seed sample transactions
INSERT INTO transactions (tenant_id, txn_date, description, debit, credit, category, source)
VALUES 
    ('demo-tenant-001', CURRENT_DATE - INTERVAL '5 days', 'AWS EC2', 18000.00, 0, 'infrastructure', 'bank'),
    ('demo-tenant-001', CURRENT_DATE - INTERVAL '3 days', 'Vercel Pro', 5000.00, 0, 'infrastructure', 'bank'),
    ('demo-tenant-001', CURRENT_DATE - INTERVAL '2 days', 'Slack Business', 2000.00, 0, 'communication', 'bank'),
    ('demo-tenant-001', CURRENT_DATE - INTERVAL '1 day', 'Customer Payment', 0, 50000.00, 'revenue', 'razorpay')
ON CONFLICT (tenant_id, external_id) DO NOTHING;

-- Verify seed data
SELECT 'Founders:' as table_name, COUNT(*) as row_count FROM founders WHERE tenant_id = 'demo-tenant-001'
UNION ALL
SELECT 'Vendor Baselines:', COUNT(*) FROM vendor_baselines WHERE tenant_id = 'demo-tenant-001'
UNION ALL
SELECT 'Finance Snapshots:', COUNT(*) FROM finance_snapshots WHERE tenant_id = 'demo-tenant-001'
UNION ALL
SELECT 'Transactions:', COUNT(*) FROM transactions WHERE tenant_id = 'demo-tenant-001';
