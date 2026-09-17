-- Channel adapters store messaging-window counters and last inbound timestamps
-- on the conversation (Instagram 24h, TikTok 48h / 10-message policy).

ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_conversations_external_user
    ON conversations (agent_id, channel, external_user_id);
