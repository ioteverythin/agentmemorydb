"""Row Level Security migration — multi-tenant memory isolation.

Inspired by InsForge's core RLS architecture with role-based access.
Adds PostgreSQL Row Level Security policies so each tenant can only
access their own memories, events, and observations at the DB level.

Revision ID: 004_add_rls
"""

from alembic import op

revision = "004_add_rls"
down_revision = "003_add_consolidation"  # adjust to your actual chain
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Create application roles ────────────────────────────
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agentmemodb_anon') THEN
                CREATE ROLE agentmemodb_anon NOLOGIN;
            END IF;
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agentmemodb_user') THEN
                CREATE ROLE agentmemodb_user NOLOGIN;
            END IF;
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agentmemodb_admin') THEN
                CREATE ROLE agentmemodb_admin NOLOGIN;
            END IF;
        END$$;
    """)

    # Grant base permissions
    op.execute("GRANT USAGE ON SCHEMA public TO agentmemodb_anon, agentmemodb_user, agentmemodb_admin;")
    op.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO agentmemodb_admin;")
    op.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO agentmemodb_admin;")

    # ── Enable RLS on core tables ───────────────────────────
    tables = ["memories", "events", "observations", "memory_links", "memory_access_log"]

    for table in tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")

    # ── Memories policies ───────────────────────────────────
    # Users can only see their own memories
    op.execute("""
        CREATE POLICY memories_tenant_isolation ON memories
            USING (user_id = current_setting('app.current_user_id', true)::uuid);
    """)
    op.execute("""
        CREATE POLICY memories_insert ON memories
            FOR INSERT
            WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid);
    """)
    op.execute("""
        CREATE POLICY memories_admin_all ON memories
            TO agentmemodb_admin
            USING (true);
    """)

    # ── Events policies ─────────────────────────────────────
    op.execute("""
        CREATE POLICY events_tenant_isolation ON events
            USING (user_id = current_setting('app.current_user_id', true)::uuid);
    """)
    op.execute("""
        CREATE POLICY events_insert ON events
            FOR INSERT
            WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid);
    """)
    op.execute("""
        CREATE POLICY events_admin_all ON events
            TO agentmemodb_admin
            USING (true);
    """)

    # ── Observations policies ───────────────────────────────
    op.execute("""
        CREATE POLICY observations_tenant_isolation ON observations
            USING (user_id = current_setting('app.current_user_id', true)::uuid);
    """)
    op.execute("""
        CREATE POLICY observations_admin_all ON observations
            TO agentmemodb_admin
            USING (true);
    """)

    # ── Memory Links policies ───────────────────────────────
    # Links visible if the user owns the source memory
    op.execute("""
        CREATE POLICY links_tenant_isolation ON memory_links
            USING (
                source_memory_id IN (
                    SELECT id FROM memories
                    WHERE user_id = current_setting('app.current_user_id', true)::uuid
                )
            );
    """)
    op.execute("""
        CREATE POLICY links_admin_all ON memory_links
            TO agentmemodb_admin
            USING (true);
    """)

    # ── Access Log policies ─────────────────────────────────
    op.execute("""
        CREATE POLICY access_log_tenant_isolation ON memory_access_log
            USING (
                memory_id IN (
                    SELECT id FROM memories
                    WHERE user_id = current_setting('app.current_user_id', true)::uuid
                )
            );
    """)
    op.execute("""
        CREATE POLICY access_log_admin_all ON memory_access_log
            TO agentmemodb_admin
            USING (true);
    """)

    # ── Grant table-level permissions to roles ──────────────
    for table in tables:
        op.execute(f"GRANT SELECT ON {table} TO agentmemodb_anon;")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO agentmemodb_user;")

    # ── Helper function: set tenant context ─────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION set_tenant_context(tenant_user_id uuid)
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        AS $$
        BEGIN
            PERFORM set_config('app.current_user_id', tenant_user_id::text, true);
        END;
        $$;
    """)

    op.execute("GRANT EXECUTE ON FUNCTION set_tenant_context(uuid) TO agentmemodb_user, agentmemodb_admin;")


def downgrade() -> None:
    # Drop helper function
    op.execute("DROP FUNCTION IF EXISTS set_tenant_context(uuid);")

    # Drop all policies
    policies = [
        ("memories", "memories_tenant_isolation"),
        ("memories", "memories_insert"),
        ("memories", "memories_admin_all"),
        ("events", "events_tenant_isolation"),
        ("events", "events_insert"),
        ("events", "events_admin_all"),
        ("observations", "observations_tenant_isolation"),
        ("observations", "observations_admin_all"),
        ("memory_links", "links_tenant_isolation"),
        ("memory_links", "links_admin_all"),
        ("memory_access_log", "access_log_tenant_isolation"),
        ("memory_access_log", "access_log_admin_all"),
    ]
    for table, policy in policies:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")

    # Disable RLS
    tables = ["memories", "events", "observations", "memory_links", "memory_access_log"]
    for table in tables:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    # Drop roles
    op.execute("DROP ROLE IF EXISTS agentmemodb_anon;")
    op.execute("DROP ROLE IF EXISTS agentmemodb_user;")
    op.execute("DROP ROLE IF EXISTS agentmemodb_admin;")
