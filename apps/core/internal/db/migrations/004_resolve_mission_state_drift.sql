-- 004_resolve_mission_state_drift.sql
-- Reconcile mission_state → mission_states schema drift

-- Step 1: Add all missing fields to mission_states that Go needs to read
ALTER TABLE mission_states
  ADD COLUMN IF NOT EXISTS prepared_brief     TEXT,
  ADD COLUMN IF NOT EXISTS pending_decisions  JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS last_updated_by    TEXT,
  ADD COLUMN IF NOT EXISTS founder_focus      TEXT,
  ADD COLUMN IF NOT EXISTS active_alerts      JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS burn_severity      TEXT,
  ADD COLUMN IF NOT EXISTS mrr_trend          TEXT,
  ADD COLUMN IF NOT EXISTS churn_rate         NUMERIC,
  ADD COLUMN IF NOT EXISTS churn_risk_users   INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS top_feature_ask    TEXT,
  ADD COLUMN IF NOT EXISTS error_spike        BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS burn_alert         BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS trust_score        INTEGER,
  ADD COLUMN IF NOT EXISTS burn_multiple      DECIMAL(5,2),
  ADD COLUMN IF NOT EXISTS effective_runway_days INTEGER;

-- Step 2: Drop old singular table (after verifying no other references)
DROP TABLE IF EXISTS mission_state;

-- Step 3: Create view for backward compat
CREATE OR REPLACE VIEW mission_state AS
  SELECT * FROM mission_states;
