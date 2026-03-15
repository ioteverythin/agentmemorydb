#!/bin/sh
set -e

# ═══════════════════════════════════════════════════════════
# AgentMemoryDB — Docker Entrypoint
# ═══════════════════════════════════════════════════════════
# Usage:
#   docker run agentmemorydb serve        → run API server (default)
#   docker run agentmemorydb migrate      → run migrations only
#   docker run agentmemorydb shell        → Python REPL
#   docker run agentmemorydb <any-cmd>    → pass through

echo "🧠 AgentMemoryDB v0.1.0"
echo "───────────────────────────"

case "${1}" in
  serve)
    echo "→ Running Alembic migrations..."
    alembic upgrade head 2>&1 || echo "⚠  Migration failed (DB may not be ready yet)"
    echo "→ Starting uvicorn on 0.0.0.0:8100..."
    exec uvicorn app.main:app \
      --host 0.0.0.0 \
      --port 8100 \
      --workers "${UVICORN_WORKERS:-1}" \
      --log-level "${LOG_LEVEL:-info}" \
      --access-log
    ;;

  serve-dev)
    echo "→ Running Alembic migrations..."
    alembic upgrade head 2>&1 || echo "⚠  Migration failed"
    echo "→ Starting uvicorn in reload mode..."
    exec uvicorn app.main:app \
      --host 0.0.0.0 \
      --port 8100 \
      --reload \
      --log-level debug
    ;;

  migrate)
    echo "→ Running Alembic migrations..."
    exec alembic upgrade head
    ;;

  downgrade)
    echo "→ Downgrading one revision..."
    exec alembic downgrade -1
    ;;

  shell)
    echo "→ Starting Python shell..."
    exec python
    ;;

  *)
    exec "$@"
    ;;
esac
