-- infra/postgres/init.sql
-- ==============================================================================
-- PostgreSQL initialization script.
-- Runs once on first container creation (before Alembic migrations).
-- Purpose: Set database-level settings only — Alembic handles schema.
-- ==============================================================================

-- Set default timezone for the database
ALTER DATABASE supplier_crm SET timezone TO 'UTC';

-- Set default text search configuration
ALTER DATABASE supplier_crm SET default_text_search_config TO 'pg_catalog.english';

-- Performance settings for connection pooling (recommended with asyncpg)
ALTER SYSTEM SET max_connections = 200;
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
ALTER SYSTEM SET random_page_cost = 1.1;  -- SSD-optimised

SELECT pg_reload_conf();
