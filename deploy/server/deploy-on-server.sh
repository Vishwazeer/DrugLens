#!/usr/bin/env bash
# DrugLens — safe, isolated deploy onto a server that ALREADY runs another
# production app (here: "gutlab" = nginx :80/:443 -> node :8080 via pm2).
#
# Guarantees:
#   * Never touches nginx, pm2, /var/www, :80, :443 or :8080.
#   * Runs as its own unix user (druglens) in its own dir (/opt/druglens).
#   * systemd MemoryMax caps it, so it can never starve the existing app.
#   * Nothing is compiled here: the React app ships prebuilt.
#   * Aborts if anything looks unsafe, and verifies the prod app afterwards.
#
# Run INSIDE the ssh session:
#   bash /tmp/deploy-on-server.sh

set -euo pipefail

TARBALL="${TARBALL:-/tmp/druglens-deploy.tar.gz}"
APP_USER="druglens"
APP_HOME="/opt/druglens"
APP_DIR="$APP_HOME/app"
ENV_FILE="/etc/druglens/druglens.env"
PORT="${PORT:-8000}"

ok()   { echo -e "  \033[1;32m✓\033[0m $*"; }
info() { echo -e "\n\033[1;36m==> $*\033[0m"; }
die()  { echo -e "\n\033[1;31mABORTED: $*\033[0m" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 0. Snapshot the EXISTING production app so we can prove we didn't break it
# ---------------------------------------------------------------------------
info "Recording current state of the existing production app"
BEFORE_NGINX=$(systemctl is-active nginx 2>/dev/null || echo "absent")
BEFORE_PM2=$(systemctl is-active pm2-gutlab 2>/dev/null || echo "absent")
echo "  nginx:       $BEFORE_NGINX"
echo "  pm2-gutlab:  $BEFORE_PM2"

# ---------------------------------------------------------------------------
# 1. Pre-flight safety checks — bail out rather than risk the prod app
# ---------------------------------------------------------------------------
info "Pre-flight safety checks"

[ -f "$TARBALL" ] || die "$TARBALL not found. scp it up first."
ok "deployment package present"

if sudo ss -tulpn 2>/dev/null | grep -q ":$PORT "; then
    die "port $PORT is already in use. Re-run with: PORT=8001 bash $0"
fi
ok "port $PORT is free (not stealing it from anything)"

for p in /etc/nginx /var/www; do
    [ -e "$p" ] && echo "  (note: $p exists and will NOT be touched)"
done
ok "will not modify nginx, pm2, /var/www, :80, :443 or :8080"

AVAIL_MB=$(free -m | awk '/^Mem:/{print $7}')
[ "$AVAIL_MB" -lt 300 ] && die "only ${AVAIL_MB}MB RAM available — too tight, not risking the prod app"
ok "RAM available: ${AVAIL_MB}MB (DrugLens is capped at 512MB)"

# ---------------------------------------------------------------------------
# 2. Dedicated user + isolated directory (NOT inside gutlab's home)
# ---------------------------------------------------------------------------
info "Creating isolated service user '$APP_USER'"
if id -u "$APP_USER" >/dev/null 2>&1; then
    ok "user already exists"
else
    sudo useradd --system --create-home --home-dir "$APP_HOME" \
                 --shell /usr/sbin/nologin "$APP_USER"
    ok "created system user '$APP_USER' (no shell, no login)"
fi

# ---------------------------------------------------------------------------
# 3. Unpack the prebuilt app
# ---------------------------------------------------------------------------
info "Installing application to $APP_DIR"
sudo rm -rf "$APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo tar -xzf "$TARBALL" -C "$APP_DIR"
sudo chown -R "$APP_USER:$APP_USER" "$APP_HOME"
ok "unpacked $(sudo find "$APP_DIR" -type f | wc -l) files (React UI ships prebuilt — nothing compiled here)"

# ---------------------------------------------------------------------------
# 4. Python venv (self-contained; no system packages altered)
# ---------------------------------------------------------------------------
info "Creating Python venv + installing dependencies"
sudo -u "$APP_USER" python3 -m venv "$APP_HOME/venv"
sudo -u "$APP_USER" "$APP_HOME/venv/bin/pip" install --quiet --upgrade pip
sudo -u "$APP_USER" "$APP_HOME/venv/bin/pip" install --quiet -r "$APP_DIR/requirements-server.txt"
ok "installed: $(sudo -u "$APP_USER" "$APP_HOME/venv/bin/pip" list 2>/dev/null | wc -l) packages into an isolated venv"

# ---------------------------------------------------------------------------
# 5. Secrets — prompted, never echoed, never in git or shell history
# ---------------------------------------------------------------------------
info "Configuring the Fireworks API key"
sudo mkdir -p "$(dirname "$ENV_FILE")"
if sudo test -f "$ENV_FILE" && sudo grep -q '^FIREWORKS_API_KEY=.\+' "$ENV_FILE" \
   && ! sudo grep -q 'PUT_YOUR_KEY_HERE' "$ENV_FILE"; then
    ok "key already configured — leaving $ENV_FILE alone"
else
    echo -n "  Paste your Fireworks API key (input hidden, press Enter): "
    read -rs FW_KEY
    echo
    [ -n "$FW_KEY" ] || die "no key entered"
    sudo tee "$ENV_FILE" > /dev/null <<EOF
FIREWORKS_API_KEY=$FW_KEY
REPORT_MODEL=accounts/fireworks/models/deepseek-v4-pro
REPORT_JSON_MODE=true
REPORT_MAX_TOKENS=4096
USE_LLM_PARSER=false
USE_TXGEMMA=false
USE_GEMMA4=true
EOF
    unset FW_KEY
    ok "key written to $ENV_FILE"
fi
sudo chown root:"$APP_USER" "$ENV_FILE"
sudo chmod 640 "$ENV_FILE"
ok "permissions locked to root:$APP_USER 640"

# ---------------------------------------------------------------------------
# 6. systemd unit with hard resource caps
# ---------------------------------------------------------------------------
info "Installing systemd service (memory-capped)"
sudo tee /etc/systemd/system/druglens.service > /dev/null <<EOF
[Unit]
Description=DrugLens - polypharmacy risk analyzer (isolated from gutlab)
After=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_HOME/venv/bin/uvicorn api:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3

# Safety rails: DrugLens can NEVER starve the existing production app.
MemoryMax=512M
MemoryHigh=400M
CPUQuota=70%

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_HOME

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --quiet druglens
sudo systemctl restart druglens
ok "service installed and started"

# ---------------------------------------------------------------------------
# 7. Health check
# ---------------------------------------------------------------------------
info "Health check"
for i in $(seq 1 15); do
    if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
        ok "API responding on 127.0.0.1:$PORT"
        break
    fi
    [ "$i" = 15 ] && { sudo journalctl -u druglens -n 30 --no-pager; die "app did not come up"; }
    sleep 1
done
curl -fsS "http://127.0.0.1:$PORT/" -o /dev/null && ok "React UI is being served at /"
DEMO=$(curl -fsS "http://127.0.0.1:$PORT/api/demo-cases" | head -c 30)
[ -n "$DEMO" ] && ok "demo cases endpoint OK"

# ---------------------------------------------------------------------------
# 8. PROVE the existing production app is unharmed
# ---------------------------------------------------------------------------
info "Verifying the existing production app is UNHARMED"
AFTER_NGINX=$(systemctl is-active nginx 2>/dev/null || echo "absent")
AFTER_PM2=$(systemctl is-active pm2-gutlab 2>/dev/null || echo "absent")

[ "$AFTER_NGINX" = "$BEFORE_NGINX" ] || die "nginx state CHANGED ($BEFORE_NGINX -> $AFTER_NGINX)"
[ "$AFTER_PM2" = "$BEFORE_PM2" ]     || die "pm2-gutlab state CHANGED ($BEFORE_PM2 -> $AFTER_PM2)"
ok "nginx:      $AFTER_NGINX (unchanged)"
ok "pm2-gutlab: $AFTER_PM2 (unchanged)"

for p in 80 443 8080; do
    sudo ss -tulpn | grep -q ":$p " && ok "port $p still served by the original app"
done

echo
free -h | head -2
echo
echo "-------------------------------------------------------------"
echo "  DrugLens is LIVE on port $PORT."
echo
echo "  Last step — open the port in your Linode Cloud Firewall:"
echo "    Linode -> gutlab -> Network -> Firewall (gutlab-prod)"
echo "    Add Inbound Rule: TCP / port $PORT / 0.0.0.0/0 / ACCEPT"
echo
echo "  Then visit:  http://172.105.40.61:$PORT"
echo
echo "  Manage:   sudo systemctl {status|restart|stop} druglens"
echo "  Logs:     sudo journalctl -u druglens -f"
echo "-------------------------------------------------------------"
