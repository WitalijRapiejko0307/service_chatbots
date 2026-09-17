-- Secrets table for encrypted tokens (PostgreSQL backend)
CREATE TABLE IF NOT EXISTS secrets (
    key VARCHAR(500) PRIMARY KEY,
    value_encrypted TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
