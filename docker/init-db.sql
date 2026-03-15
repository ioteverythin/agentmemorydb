-- ═══════════════════════════════════════════════════════════
-- AgentMemoryDB — PostgreSQL Initialization
-- ═══════════════════════════════════════════════════════════
-- This runs once when the Postgres container is first created.
-- It enables the pgvector and uuid-ossp extensions.

-- Enable pgvector for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable uuid-ossp for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pg_trgm for fuzzy text search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Confirm extensions are loaded
DO $$
BEGIN
  RAISE NOTICE 'AgentMemoryDB: Extensions loaded — vector, uuid-ossp, pg_trgm';
END $$;
