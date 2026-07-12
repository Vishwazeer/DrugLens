#!/usr/bin/env bash
# DrugLens — native deploy on a Ubuntu/Debian server (no Docker).
#
# Serves the FastAPI API *and* the built React UI from a single uvicorn
# process on 127.0.0.1:8000, fronted by Caddy for HTTPS.
#
# Usage (as a sudo-capable user):
#   sudo bash deploy/server/install.sh
#
# Re-running is safe: it pulls, rebuilds, and restarts.

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/druglens}"
REPO_URL="${REPO_URL:-https://github.com/Vishwazeer/DrugLens.git}"
BRANCH="${BRANCH:-main}"
SERVICE_USER="${SERVICE_USER:-druglens}"
ENV_FILE="/etc/druglens/druglens.env"

log() { echo -e "\n\033[1;36m==> $*\033[0m"; }

# ---------------------------------------------------------------- prerequisites
log "Installing system packages"
apt-get update -qq
apt-get install -y --no-install-recommends \
    git curl ca-certificates python3 python3-venv python3-pip

# Node 22 (needed to build the React frontend)
if ! command -v node >/dev/null 2>&1 || [ "$(node -v | cut -c2-3)" -lt 20 ]; then
    log "Installing Node.js 22"
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y nodejs
fi
log "Node $(node -v) | npm $(npm -v) | Python $(python3 --version)"

# ---------------------------------------------------------------- service user
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    log "Creating service user: $SERVICE_USER"
    useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

# ---------------------------------------------------------------- source
if [ -d "$APP_DIR/.git" ]; then
    log "Updating existing checkout at $APP_DIR"
    git -C "$APP_DIR" fetch origin --quiet
    git -C "$APP_DIR" checkout "$BRANCH" --quiet
    git -C "$APP_DIR" reset --hard "origin/$BRANCH" --quiet
else
    log "Cloning $REPO_URL -> $APP_DIR"
    mkdir -p "$(dirname "$APP_DIR")"
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

# ---------------------------------------------------------------- secrets
mkdir -p "$(dirname "$ENV_FILE")"
if [ ! -f "$ENV_FILE" ]; then
    log "Creating $ENV_FILE — you MUST put your Fireworks key in it"
    cat > "$ENV_FILE" <<'EOF'
# DrugLens runtime configuration (read by systemd, never committed to git)
FIREWORKS_API_KEY=PUT_YOUR_KEY_HERE
REPORT_MODEL=accounts/fireworks/models/deepseek-v4-pro
REPORT_JSON_MODE=true
REPORT_MAX_TOKENS=4096
# CPU host: no local vLLM, so keep the local Gemma models off
USE_LLM_PARSER=false
USE_TXGEMMA=false
USE_GEMMA4=true
EOF
fi
chmod 600 "$ENV_FILE"
chown root:root "$ENV_FILE"

# ---------------------------------------------------------------- python deps
log "Creating Python venv + installing backend deps"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# ---------------------------------------------------------------- frontend build
# VITE_API_URL="" => the built app calls the SAME origin, which FastAPI serves.
log "Building the React frontend (this takes ~1-2 min)"
cd "$APP_DIR/frontend"
npm ci --silent
VITE_API_URL="" npm run build
cd "$APP_DIR"
[ -d "$APP_DIR/frontend/dist" ] || { echo "FATAL: frontend/dist was not produced"; exit 1; }

chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

# ---------------------------------------------------------------- systemd
log "Installing systemd unit"
install -m 644 "$APP_DIR/deploy/server/druglens.service" /etc/systemd/system/druglens.service
systemctl daemon-reload
systemctl enable --quiet druglens
systemctl restart druglens

sleep 3
if systemctl is-active --quiet druglens; then
    log "druglens service is RUNNING"
else
    echo "Service failed to start. Logs:"; journalctl -u druglens -n 30 --no-pager; exit 1
fi

# ---------------------------------------------------------------- health check
log "Health check"
if curl -fsS http://127.0.0.1:8000/api/health; then
    echo -e "\n\nDrugLens is up on 127.0.0.1:8000"
else
    echo "Health check FAILED"; journalctl -u druglens -n 30 --no-pager; exit 1
fi

cat <<EOF

--------------------------------------------------------------------
NEXT STEPS
  1. Put your real key in:  $ENV_FILE
     then:  sudo systemctl restart druglens
  2. Expose it publicly with HTTPS:
       sudo bash $APP_DIR/deploy/server/setup-https.sh <your-subdomain>.duckdns.org
     (or just open port 8000 and use http://<your-ip>:8000 for plain HTTP)
--------------------------------------------------------------------
EOF
