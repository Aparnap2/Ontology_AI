-- TrackGuard v4.2 Internal Ops Schema Extensions
-- Migration 008: 6 Desks (Finance, People, Legal, Intelligence, IT, Admin)
-- Append-only: No destructive changes to existing tables

-- ═══════════════════════════════════════════════════════════════════════════════
-- Finance Desk: AR/AP, payroll events, reconciliation
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS finance_ops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id UUID NOT NULL REFERENCES founders(id) ON DELETE CASCADE,
    task_type VARCHAR(50) NOT NULL, -- 'ar_reminder', 'ap_due', 'payroll_prep', 'reconciliation'
    payload JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(30) DEFAULT 'pending', -- 'pending', 'completed', 'auto_executed'
    due_date TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finance_ops_founder ON finance_ops(founder_id);
CREATE INDEX IF NOT EXISTS idx_finance_ops_status ON finance_ops(status);
CREATE INDEX IF NOT EXISTS idx_finance_ops_due ON finance_ops(due_date);

-- ═══════════════════════════════════════════════════════════════════════════════
-- People Desk: Onboarding, leave, appraisals, offboarding
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS people_ops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id UUID NOT NULL REFERENCES founders(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL, -- 'onboarding', 'leave_request', 'appraisal', 'offboarding'
    employee_name VARCHAR(200),
    payload JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(30) DEFAULT 'pending',
    event_date TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_people_ops_founder ON people_ops(founder_id);
CREATE INDEX IF NOT EXISTS idx_people_ops_type ON people_ops(event_type);

-- ═══════════════════════════════════════════════════════════════════════════════
-- Legal Desk: Documents, eSign, expiry alerts, compliance filings
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS legal_ops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id UUID NOT NULL REFERENCES founders(id) ON DELETE CASCADE,
    document_type VARCHAR(100) NOT NULL, -- 'nda', 'contract', 'compliance_filing'
    document_name VARCHAR(300),
    expiry_date TIMESTAMPTZ,
    esign_status VARCHAR(30), -- 'pending', 'signed', 'expired'
    payload JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(30) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_legal_ops_founder ON legal_ops(founder_id);
CREATE INDEX IF NOT EXISTS idx_legal_ops_expiry ON legal_ops(expiry_date);

-- ═══════════════════════════════════════════════════════════════════════════════
-- IT & Tools Desk: SaaS subscriptions, cloud spend, hardware assets
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS it_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id UUID NOT NULL REFERENCES founders(id) ON DELETE CASCADE,
    asset_type VARCHAR(50) NOT NULL, -- 'saas_subscription', 'cloud_resource', 'hardware'
    asset_name VARCHAR(300) NOT NULL,
    monthly_cost NUMERIC(10,2),
    last_used_date TIMESTAMPTZ,
    renewal_date TIMESTAMPTZ,
    payload JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(30) DEFAULT 'active', -- 'active', 'unused', 'cancelled'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_it_assets_founder ON it_assets(founder_id);
CREATE INDEX IF NOT EXISTS idx_it_assets_status ON it_assets(status);

-- ═══════════════════════════════════════════════════════════════════════════════
-- Admin Desk: Meetings, action items, SOPs, announcements
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS admin_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id UUID NOT NULL REFERENCES founders(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL, -- 'meeting', 'action_item', 'sop', 'announcement'
    title VARCHAR(300),
    payload JSONB NOT NULL DEFAULT '{}',
    meeting_date TIMESTAMPTZ,
    action_items JSONB DEFAULT '[]',
    sop_reference VARCHAR(300),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_events_founder ON admin_events(founder_id);
CREATE INDEX IF NOT EXISTS idx_admin_events_type ON admin_events(event_type);

-- ═══════════════════════════════════════════════════════════════════════════════
-- Schema Documentation Comments
-- ═══════════════════════════════════════════════════════════════════════════════

COMMENT ON TABLE finance_ops IS 'TrackGuard v4.2 Internal Ops — Finance Desk (AR/AP, payroll)';
COMMENT ON TABLE people_ops IS 'TrackGuard v4.2 Internal Ops — People Desk (HR, onboarding)';
COMMENT ON TABLE legal_ops IS 'TrackGuard v4.2 Internal Ops — Legal Desk (contracts, compliance)';
COMMENT ON TABLE it_assets IS 'TrackGuard v4.2 Internal Ops — IT & Tools Desk (SaaS, cloud)';
COMMENT ON TABLE admin_events IS 'TrackGuard v4.2 Internal Ops — Admin Desk (meetings, SOPs)';

-- Comment: This migration adds:
-- - finance_ops: Track AR/AP reminders, payroll prep, reconciliation tasks
-- - people_ops: Track onboarding, leave requests, appraisals, offboarding
-- - legal_ops: Track contracts, NDAs, compliance filings, eSign status
-- - it_assets: Track SaaS subscriptions, cloud resources, hardware
-- - admin_events: Track meetings, action items, SOPs, announcements

-- ═══════════════════════════════════════════════════════════════════════════════
-- Auto-update updated_at Triggers
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_finance_ops_updated_at
    BEFORE UPDATE ON finance_ops
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_people_ops_updated_at
    BEFORE UPDATE ON people_ops
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_legal_ops_updated_at
    BEFORE UPDATE ON legal_ops
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_it_assets_updated_at
    BEFORE UPDATE ON it_assets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_admin_events_updated_at
    BEFORE UPDATE ON admin_events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
