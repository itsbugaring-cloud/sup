#!/bin/bash
# ==============================================================================
# Supplier CRM — VPS Deploy Script
# Usage:
#   bash deploy.sh             → full rebuild (when Python deps changed)
#   bash deploy.sh --static    → copy static files only (fast, no rebuild)
# ==============================================================================

set -e

APP_DIR="/home/erka51/supplier-crm"
CONTAINER="crm_backend"
STATIC_DIR="backend/static"

cd "$APP_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Supplier CRM Deploy Script"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "→ Pulling latest from GitHub..."
git pull origin main

if [[ "$1" == "--static" ]]; then
    echo "→ [FAST MODE] Copying static files directly into container..."
    docker cp "$STATIC_DIR/." "$CONTAINER:/app/static/"
    echo "✓ Static files updated without rebuild."
else
    echo "→ Building Docker image (full rebuild)..."
    docker compose build backend --no-cache
    echo "→ Restarting backend container..."
    docker compose up -d backend
    echo "✓ Full rebuild and deploy complete."
fi

echo ""
echo "→ Container status:"
docker ps --filter "name=$CONTAINER" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "✓ Deploy finished at $(date '+%Y-%m-%d %H:%M:%S')"
