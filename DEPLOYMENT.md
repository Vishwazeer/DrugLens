# 🚀 DrugLens — Deployment

Live: **http://172.105.40.61:8000**

The public demo runs on a Linode VM (Ubuntu 24.04, 1 vCPU / 2 GB RAM) that
**already hosts an unrelated production application** (`gutlab`: nginx on
:80/:443 → a Node app on :8080 via pm2). Everything below is designed so that
DrugLens **cannot disturb it**.

---

## Architecture of the deployment

One `uvicorn` process serves **both** the API and the built React UI on a single
origin, so there is no CORS surface and no second web server:

```
Internet ──► :8000 ──► uvicorn (user: druglens)
                        ├── /api/*   FastAPI  (api.py)
                        └── /        StaticFiles → frontend/dist   (built React)
```

`api.py` mounts `frontend/dist` at `/` only if that directory exists, so the same
code runs in local dev (Vite serves the UI separately) and in production.

---

## Isolation from the co-hosted production app

This was a hard requirement: **the existing `gutlab` app must never be affected.**

| Concern | How it is handled |
|---|---|
| **Process identity** | Runs as a dedicated system user **`druglens`** (`/usr/sbin/nologin`… later given `/bin/bash` for SSH). Never `root`, never `gutlab`. |
| **Filesystem** | Lives entirely in `/opt/druglens`. Nothing in `/home/gutlab`, nothing in `/var/www`. |
| **Ports** | Binds **:8000** only. Never touches :80, :443 or :8080. |
| **Web server** | nginx is **not modified**. DrugLens serves itself; it is not proxied. |
| **Memory** | systemd `MemoryMax=512M`, `MemoryHigh=400M`, `CPUQuota=70%`. If DrugLens ever misbehaves the kernel kills **DrugLens**, not the production app. (Actual usage: ~60–80 MB.) |
| **Privileges** | `druglens` has **no sudo** and cannot escalate. |
| **Secrets** | `/etc/druglens/druglens.env`, mode `640`, owner `root:druglens` — the `gutlab` user cannot read the API key. |
| **Build load** | **Nothing is compiled on the server.** The React app is built locally and shipped as a ~140 KB tarball. On a 2 GB box a Vite build could OOM-kill the neighbouring production app. |

The deploy script (`deploy/server/deploy-on-server.sh`) snapshots nginx/pm2 state
before it runs, refuses to start if port 8000 is taken or RAM is low, and
**re-verifies that nginx and pm2-gutlab are still active afterwards**, aborting if
anything changed.

---

## First-time install

```bash
# 1. (local) build the deployment package — nothing is compiled on the server
cd frontend && VITE_API_URL="" npm run build && cd ..
#    package: api.py, src/, data/, frontend/dist/, requirements-server.txt

# 2. upload
scp druglens-deploy.tar.gz    gutlab@<host>:/tmp/
scp deploy/server/deploy-on-server.sh gutlab@<host>:/tmp/

# 3. (on the server, as a sudo-capable user) run it
bash /tmp/deploy-on-server.sh
```

It creates the `druglens` user, unpacks to `/opt/druglens/app`, builds an isolated
venv, prompts for the Fireworks key (hidden input), installs the memory-capped
systemd unit, health-checks the app, and proves the production app is unharmed.

### Open the port
Two firewalls stack on this host — **both** must allow 8000:

1. **Linode Cloud Firewall** → Inbound rule: TCP / 8000 / `0.0.0.0/0` / ACCEPT → **Save Changes**
2. **Host `ufw`**:
   ```bash
   sudo ufw allow 8000/tcp comment 'druglens'
   ```

---

## Redeploying an update

```bash
# local: rebuild the UI and package
cd frontend && VITE_API_URL="" npm run build && cd ..
tar -czf druglens-deploy.tar.gz api.py src data frontend/dist requirements-server.txt

# ship it (druglens owns /opt/druglens, so no sudo needed for the swap)
scp druglens-deploy.tar.gz druglens@<host>:/opt/druglens/
ssh druglens@<host> '
  cd /opt/druglens
  rm -rf app.new && mkdir app.new
  tar -xzf druglens-deploy.tar.gz -C app.new
  rm -rf app.old && mv app app.old && mv app.new app     # app.old = instant rollback
'

# restart (needs sudo — druglens deliberately has none)
ssh gutlab@<host> 'sudo systemctl restart druglens'
```

**Rollback:** `mv app app.broken && mv app.old app && sudo systemctl restart druglens`

---

## Configuration

`/etc/druglens/druglens.env` (root:druglens, 640 — never in git):

| Variable | Purpose |
|---|---|
| `FIREWORKS_API_KEY` | Cloud inference. Without it the deterministic engine still works via rule-based fallbacks. |
| `REPORT_MODEL` | Cloud model id. Default `accounts/fireworks/models/deepseek-v4-pro`. |
| `REPORT_MODEL_FALLBACKS` | Optional, comma-separated. Tried **before** `REPORT_MODEL`; the first model that works is cached. Lets you put a preferred model in front without risking the demo — if it fails, the app silently falls back. |
| `REPORT_JSON_MODE` | Forces structured-JSON responses. Keep `true`: reasoning models otherwise emit chain-of-thought and break parsing. |
| `REPORT_MAX_TOKENS` | Default `4096`. Reasoning models spend a large, variable share on hidden reasoning; too small a budget truncates the output. |
| `USE_LLM_PARSER` / `USE_TXGEMMA` | Local MedGemma / TxGemma via vLLM. **`false`** on CPU hosts — if left `true` the API tries to reach vLLM servers that do not exist and every request hangs 30–60 s. |
| `USE_GEMMA4` | Cloud report generation. |

---

## Operations

```bash
sudo systemctl status druglens      # state
sudo systemctl restart druglens     # restart
sudo journalctl -u druglens -f      # live logs

curl http://127.0.0.1:8000/api/health         # liveness
curl http://127.0.0.1:8000/api/engine-stats   # real ruleset counts + measured latency
```

### Verify the production app is unharmed
```bash
systemctl is-active nginx pm2-gutlab      # both must be "active"
systemctl show nginx -p NRestarts         # must still be 0
sudo ss -tulpn | grep -E ':(80|443|8080)'  # still owned by the original app
curl -s -o /dev/null -w '%{http_code}' -k https://<host>/   # 200
```

---

## Gotchas we hit (so you don't)

- **`python3-venv` was missing.** `python3 -m venv --help` succeeds even when the
  `python3.12-venv` apt package is absent — the failure only appears at
  `ensurepip`. Fix: `sudo apt-get install -y python3.12-venv` (installs 3 packages,
  upgrades nothing).
- **Two stacked firewalls.** Opening the Linode Cloud Firewall is not enough; host
  `ufw` silently drops the port as well. Both must allow it.
- **Do NOT `chmod 750 /var/www/gutlab`.** nginx runs as `www-data`, which is not in
  the `gutlab` group, so it immediately 403s the production site. If you want to
  stop `druglens` reading it, add nginx to the group *first*:
  `sudo usermod -aG gutlab www-data && sudo chmod 750 /var/www/gutlab && sudo systemctl reload nginx` — then confirm HTTP 200.
- **Don't build on the server.** 2 GB RAM shared with a production app; a Vite/TS
  build can OOM. Build locally, ship `dist/`.
- **The frontend must send `use_llm_parser: false` / `use_txgemma: false`** on CPU
  hosts (the API now defaults them from `config`), otherwise every analysis waits
  on non-existent local vLLM servers.

---

## Container / Space deployment (alternative)

- `Dockerfile` — multi-stage: Node builds the React app, then FastAPI serves the API
  **and** the built UI from one image on :8000. Runs as a non-root user (uid 1000),
  which also makes it Hugging Face Spaces-compatible.
- `docker compose --profile cpu-only up --build` — app only.
- `docker compose --profile gpu up --build` — adds MedGemma + TxGemma on vLLM/ROCm.
- `deploy/hf-space/` — Space metadata + a push script that ships only the app files
  (the repo's demo video exceeds the Hub's 10 MB non-LFS limit).
