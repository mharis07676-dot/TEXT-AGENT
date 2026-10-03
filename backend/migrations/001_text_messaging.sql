-- Text Agent messaging schema (PostgreSQL)
-- Apply with: psql "$DATABASE_URL_SYNC" -f backend/migrations/001_text_messaging.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

DO $$ BEGIN
    CREATE TYPE userrole AS ENUM ('owner', 'admin', 'agent', 'viewer');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE messagingchannel AS ENUM ('sms', 'whatsapp');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE conversationstatus AS ENUM ('active', 'closed', 'archived');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE messagerole AS ENUM ('user', 'assistant', 'human', 'system');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE messagedirection AS ENUM ('inbound', 'outbound');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE messagingprovidername AS ENUM ('twilio');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE preferredlanguage AS ENUM ('english', 'roman_urdu', 'urdu', 'unknown');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    is_active BOOLEAN DEFAULT TRUE,
    settings JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role userrole DEFAULT 'agent',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_users_tenant_email UNIQUE (tenant_id, email)
);
CREATE INDEX IF NOT EXISTS ix_users_tenant_id ON users(tenant_id);

CREATE TABLE IF NOT EXISTS contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    phone_number VARCHAR(32) NOT NULL,
    name VARCHAR(255),
    preferred_language preferredlanguage DEFAULT 'unknown',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_contacts_tenant_phone UNIQUE (tenant_id, phone_number)
);
CREATE INDEX IF NOT EXISTS ix_contacts_tenant_id ON contacts(tenant_id);
CREATE INDEX IF NOT EXISTS ix_contacts_phone_number ON contacts(phone_number);

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    contact_id UUID NOT NULL REFERENCES contacts(id),
    channel messagingchannel NOT NULL,
    status conversationstatus NOT NULL DEFAULT 'active',
    ai_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    assigned_user_id UUID REFERENCES users(id),
    last_message_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_conversations_tenant_id ON conversations(tenant_id);
CREATE INDEX IF NOT EXISTS ix_conversations_contact_id ON conversations(contact_id);
CREATE INDEX IF NOT EXISTS ix_conversations_status ON conversations(status);
CREATE INDEX IF NOT EXISTS ix_conversations_last_message_at ON conversations(last_message_at);
CREATE INDEX IF NOT EXISTS ix_conversations_assigned_user_id ON conversations(assigned_user_id);
CREATE INDEX IF NOT EXISTS ix_conversations_active_lookup
    ON conversations(tenant_id, contact_id, channel, status);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    conversation_id UUID NOT NULL REFERENCES conversations(id),
    role messagerole NOT NULL,
    direction messagedirection NOT NULL,
    channel messagingchannel NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    provider messagingprovidername NOT NULL DEFAULT 'twilio',
    provider_message_sid VARCHAR(128),
    provider_status VARCHAR(64),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_messages_provider_sid UNIQUE (provider, provider_message_sid)
);
CREATE INDEX IF NOT EXISTS ix_messages_tenant_id ON messages(tenant_id);
CREATE INDEX IF NOT EXISTS ix_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS ix_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS ix_messages_provider_message_sid ON messages(provider_message_sid);

INSERT INTO tenants (name, slug, is_active, settings)
VALUES ('Synas', 'synas', TRUE, '{}'::jsonb)
ON CONFLICT (slug) DO NOTHING;
