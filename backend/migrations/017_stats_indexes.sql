-- Indexes for admin stats and audit log date-range queries.

CREATE INDEX IF NOT EXISTS idx_conversations_created_at
    ON conversations (created_at);
