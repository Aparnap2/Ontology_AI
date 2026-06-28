-- 003_temporal_workflow_id.sql
-- Add temporal_workflow_id column to planned_actions for P1 bug #3 fix

ALTER TABLE planned_actions
  ADD COLUMN IF NOT EXISTS temporal_workflow_id TEXT;
