-- Speed up provider_message_id_exists lookups by external_message_id within a conversation.

CREATE INDEX IF NOT EXISTS idx_messages_conv_external_message_id
    ON messages (conversation_id, external_message_id);
