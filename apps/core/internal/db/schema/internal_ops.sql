-- OntologyAI v4.2 Internal Ops Schema Extensions
-- For sqlc code generation

-- Finance Desk: AR/AP, payroll events, reconciliation
CREATE TABLE IF NOT EXISTS finance_ops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id UUID REFERENCES founders(id) ON DELETE CASCADE,
    task_type VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(30) DEFAULT 'pending',
    due_date TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- People Desk: Onboarding, leave, appraisals, offboarding
CREATE TABLE IF NOT EXISTS people_ops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id UUID REFERENCES founders(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    employee_name VARCHAR(200),
    payload JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(30) DEFAULT 'pending',
    event_date TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Legal Desk: Documents, eSign, expiry alerts, compliance filings
CREATE TABLE IF NOT EXISTS legal_ops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id UUID REFERENCES founders(id) ON DELETE CASCADE,
    document_type VARCHAR(100) NOT NULL,
    document_name VARCHAR(300),
    expiry_date TIMESTAMPTZ,
    esign_status VARCHAR(30),
    payload JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(30) DEFAULT 'pending',
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- IT & Tools Desk: SaaS subscriptions, cloud spend, hardware assets
CREATE TABLE IF NOT EXISTS it_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id UUID REFERENCES founders(id) ON DELETE CASCADE,
    asset_type VARCHAR(50) NOT NULL,
    asset_name VARCHAR(300) NOT NULL,
    monthly_cost NUMERIC(10,2),
    last_used_date TIMESTAMPTZ,
    renewal_date TIMESTAMPTZ,
    payload JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(30) DEFAULT 'active',
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Admin Desk: Meetings, action items, SOPs, announcements
CREATE TABLE IF NOT EXISTS admin_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id UUID REFERENCES founders(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    title VARCHAR(300),
    payload JSONB NOT NULL DEFAULT '{}',
    meeting_date TIMESTAMPTZ,
    action_items JSONB DEFAULT '[]',
    sop_reference VARCHAR(300),
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
