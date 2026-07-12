#!/usr/bin/env bash
# Put Caddy in front of DrugLens so judges get a real HTTPS URL.
#
# You have a public IP but no domain, so use a free DuckDNS subdomain:
#   1. Sign in at https://www.duckdns.org (GitHub/Google login)
#   2. Create a subdomain, e.g. "druglens"  -> druglens.duckdns.org
#   3. Point it at this server's public IP (DuckDNS does this for you)
#   4. Run:  sudo bash deploy/server/setup-https.sh druglens.duckdns.org
#
# Caddy then fetches a free Let's Encrypt certificate automatically.
# (DuckDNS is on the Public Suffix List, so each subdomain gets its own
# certificate rate limit — unlike nip.io, which is shared and often throttled.)

set -euo pipefail

DOMAIN="${1:-}"
if [ -z "$DOMAIN" ]; then
    echo "Usage: sudo bash $0 <your-subdomain>.duckdns.org"
    exit 1
fi

log() { echo -e "\n\033[1;36m==> $*\033[0m"; }

if ! command -v caddy >/dev/null 2>&1; then
    log "Installing Caddy"
    apt-get install -y --no-install-recommends debian-keyring debian-archive-keyring apt-transport-https curl
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq
    apt-get install -y caddy
fi

log "Writing Caddyfile for $DOMAIN"
cat > /etc/caddy/Caddyfile <<EOF
$DOMAIN {
    encode gzip

    # Server-Sent Events: the clinical narrative streams for 30-60s, so the
    # proxy must not buffer the response or time the upstream out early.
    reverse_proxy 127.0.0.1:8000 {
        flush_interval -1
        transport http {
            read_timeout 300s
            write_timeout 300s
        }
    }
}
EOF

caddy validate --config /etc/caddy/Caddyfile
systemctl enable --quiet caddy
systemctl restart caddy

log "Opening firewall (if ufw is active)"
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    ufw allow 80/tcp  >/dev/null
    ufw allow 443/tcp >/dev/null
fi

sleep 4
log "Done"
cat <<EOF

  Your site:  https://$DOMAIN

  Certificate issuance takes a few seconds on first request. If it fails,
  check that $DOMAIN really resolves to this server's public IP:
      dig +short $DOMAIN
  and watch Caddy:
      journalctl -u caddy -f
EOF
