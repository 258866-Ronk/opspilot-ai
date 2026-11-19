-- ============================================================
-- OpsPilot AI 数据库初始化脚本（PostgreSQL + pgvector）
-- 本地开发默认用 SQLite（由 SQLAlchemy create_all 自动建表），
-- 本脚本用于 Docker Compose 启动 PostgreSQL 时的生产级建表。
-- ============================================================
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(128),
    nickname VARCHAR(64),
    role VARCHAR(32) NOT NULL DEFAULT 'OPERATOR',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_tasks (
    id BIGSERIAL PRIMARY KEY,
    task_no VARCHAR(64) UNIQUE NOT NULL,
    user_id BIGINT REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    service_name VARCHAR(100),
    status VARCHAR(32) NOT NULL,
    task_type VARCHAR(50),
    result JSONB,
    error_message TEXT,
    total_tokens INTEGER DEFAULT 0,
    execution_time_ms BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON agent_tasks(created_at DESC);

CREATE TABLE IF NOT EXISTS agent_steps (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT REFERENCES agent_tasks(id),
    step_no INTEGER NOT NULL,
    node_name VARCHAR(100),
    action VARCHAR(100),
    input_data JSONB,
    output_data JSONB,
    status VARCHAR(32),
    duration_ms BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tool_executions (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT REFERENCES agent_tasks(id),
    tool_name VARCHAR(100) NOT NULL,
    arguments JSONB,
    result JSONB,
    status VARCHAR(32),
    error_message TEXT,
    duration_ms BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id BIGSERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    file_path TEXT,
    file_type VARCHAR(32),
    status VARCHAR(32),
    chunk_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 向量维度 384 对应本地默认嵌入；若用 BGE-small-zh（512 维）需同步修改
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT REFERENCES knowledge_documents(id),
    content TEXT NOT NULL,
    metadata JSONB,
    embedding VECTOR(384),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON knowledge_chunks
    USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS incidents (
    id BIGSERIAL PRIMARY KEY,
    incident_no VARCHAR(64) UNIQUE NOT NULL,
    task_id BIGINT REFERENCES agent_tasks(id),
    service_name VARCHAR(100),
    severity VARCHAR(20),
    title VARCHAR(255),
    description TEXT,
    root_cause TEXT,
    status VARCHAR(32) DEFAULT 'OPEN',
    assignee VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS approvals (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT REFERENCES agent_tasks(id),
    action_name VARCHAR(100) NOT NULL,
    action_arguments JSONB,
    arguments_signature VARCHAR(128),
    risk_level VARCHAR(20),
    requested_by BIGINT REFERENCES users(id),
    reviewed_by BIGINT REFERENCES users(id),
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    review_comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    task_id BIGINT REFERENCES agent_tasks(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(100),
    detail JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC);
