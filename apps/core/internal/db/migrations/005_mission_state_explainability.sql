-- 005_mission_state_explainability.sql
-- Add explainability fields to mission_states for Paperclip-inspired visibility

ALTER TABLE mission_states
  ADD COLUMN IF NOT EXISTS last_update_reason TEXT,
  ADD COLUMN IF NOT EXISTS last_changed_fields JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS active_agent_roles JSONB DEFAULT '[]';
