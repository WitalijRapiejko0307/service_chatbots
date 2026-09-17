-- AI Agents CRM - Initial PostgreSQL schema for Railway
-- Run with: psql $DATABASE_PUBLIC_URL -f migrations/001_initial.sql
-- Note: pgvector not used - embeddings stored as JSONB for compatibility with standard PostgreSQL

-- conversations
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id VARCHAR(255) PRIMARY KEY,
    agent_id VARCHAR(255) NOT NULL,
    channel VARCHAR(50) DEFAULT 'web_chat',
    external_conversation_id VARCHAR(255),
    external_user_id VARCHAR(255),
    status VARCHAR(50) DEFAULT 'AI_ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    handoff_reason TEXT,
    request_type VARCHAR(50),
    ttl BIGINT,
    external_user_name VARCHAR(255),
    external_user_username VARCHAR(255),
    external_user_profile_pic TEXT,
    marketing_status VARCHAR(50) DEFAULT 'NEW',
    rejection_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_conversations_agent_id ON conversations(agent_id);
CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations(status);
CREATE INDEX IF NOT EXISTS idx_conversations_agent_status ON conversations(agent_id, status);

-- messages
CREATE TABLE IF NOT EXISTS messages (
    conversation_id VARCHAR(255) NOT NULL,
    message_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    channel VARCHAR(50) DEFAULT 'web_chat',
    external_message_id VARCHAR(255),
    external_user_id VARCHAR(255),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    ttl BIGINT,
    PRIMARY KEY (conversation_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);

-- agents
CREATE TABLE IF NOT EXISTS agents (
    agent_id VARCHAR(255) PRIMARY KEY,
    config JSONB NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- audit_logs
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id VARCHAR(255) PRIMARY KEY,
    admin_id VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NOT NULL,
    resource_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_admin_id ON audit_logs(admin_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource_type ON audit_logs(resource_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp DESC);

-- channel_bindings
CREATE TABLE IF NOT EXISTS channel_bindings (
    binding_id VARCHAR(255) PRIMARY KEY,
    agent_id VARCHAR(255) NOT NULL,
    channel_type VARCHAR(50) NOT NULL,
    channel_account_id VARCHAR(255) NOT NULL,
    channel_username VARCHAR(255),
    secret_name VARCHAR(500),
    encrypted_access_token TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_channel_bindings_agent_id ON channel_bindings(agent_id);
CREATE INDEX IF NOT EXISTS idx_channel_bindings_agent_channel ON channel_bindings(agent_id, channel_type);
CREATE INDEX IF NOT EXISTS idx_channel_bindings_account ON channel_bindings(channel_type, channel_account_id);

-- instagram_profiles
CREATE TABLE IF NOT EXISTS instagram_profiles (
    external_user_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255),
    username VARCHAR(255),
    profile_pic TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ttl BIGINT NOT NULL
);

-- notification_configs
CREATE TABLE IF NOT EXISTS notification_configs (
    config_id VARCHAR(255) PRIMARY KEY,
    notification_type VARCHAR(50) NOT NULL,
    bot_token_secret_name VARCHAR(500),
    encrypted_bot_token TEXT,
    chat_id VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255)
);

-- sessions (cache)
CREATE TABLE IF NOT EXISTS sessions (
    session_key VARCHAR(500) PRIMARY KEY,
    value TEXT,
    expires_at BIGINT
);

CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);

-- rag_documents (using JSONB for embedding - works without pgvector)
CREATE TABLE IF NOT EXISTS rag_documents (
    agent_id VARCHAR(255) NOT NULL,
    document_id VARCHAR(255) NOT NULL,
    title VARCHAR(500) DEFAULT '',
    content TEXT NOT NULL,
    embedding JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    PRIMARY KEY (agent_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_rag_documents_agent_id ON rag_documents(agent_id);
