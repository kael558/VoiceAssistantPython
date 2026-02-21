#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# deploy.sh -- Deploy VoiceAssistant to a Raspberry Pi via SSH
#
# Usage:
#   ./deploy.sh                            # uses defaults
#   ./deploy.sh pi@192.168.1.50            # custom user@host
#   PI_HOST=mypi.local ./deploy.sh         # env-var override
#
# First run:  syncs code, creates venv, installs deps, provisions 3 systemd
#             services (ngrok, server, webserver), enables & starts them.
# Later runs: syncs code, reinstalls deps (fast no-op if unchanged), restarts.
# ============================================================================

# ---------------------------------------------------------------------------
# Configuration  (override via env vars or first positional arg)
# ---------------------------------------------------------------------------
PI_USER="${PI_USER:-pi}"
PI_HOST="${PI_HOST:-raspberrypi.local}"
if [[ $# -ge 1 ]]; then
    if [[ "$1" == *@* ]]; then
        PI_USER="${1%%@*}"
        PI_HOST="${1#*@}"
    else
        PI_HOST="$1"
    fi
fi
PI_TARGET="${PI_USER}@${PI_HOST}"

REMOTE_DIR="${REMOTE_DIR:-/home/${PI_USER}/Desktop/VoiceAssistantPython}"
VENV_DIR="${REMOTE_DIR}/venv"
PYTHON="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"

NGROK_DOMAIN="${NGROK_DOMAIN:-robust-classic-trout.ngrok-free.app}"
NGROK_BIN="${NGROK_BIN:-/usr/local/bin/ngrok}"

LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERR]${NC}   $*"; }

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
info "Target: ${PI_TARGET}:${REMOTE_DIR}"

command -v rsync &>/dev/null || { err "rsync not found -- install it first"; exit 1; }
ssh -o ConnectTimeout=5 -o BatchMode=yes "${PI_TARGET}" true 2>/dev/null \
    || { err "Cannot SSH to ${PI_TARGET}. Check host/user/key."; exit 1; }
ok "SSH connection verified"

# ---------------------------------------------------------------------------
# 1. Sync project files  (never overwrites .env or persistent data)
# ---------------------------------------------------------------------------
info "Syncing project files..."

rsync -avz --delete \
    --exclude '.env' \
    --exclude 'venv/' \
    --exclude '__pycache__/' \
    --exclude '.idea/' \
    --exclude '.git/' \
    --exclude '.cursor/' \
    --exclude '.gitignore' \
    --exclude 'data/conversations/' \
    --exclude 'data/uber_browser_profile/' \
    --exclude '*.log' \
    --exclude '*.pyc' \
    --exclude 'ngrok.exe' \
    --exclude '.mypy_cache/' \
    --exclude '.pytest_cache/' \
    "${LOCAL_DIR}/" "${PI_TARGET}:${REMOTE_DIR}/"

ok "Files synced"

# ---------------------------------------------------------------------------
# 2. Copy .env if it doesn't exist on the Pi yet
# ---------------------------------------------------------------------------
ENV_EXISTS=$(ssh "${PI_TARGET}" "test -f '${REMOTE_DIR}/.env' && echo yes || echo no")
if [[ "$ENV_EXISTS" == "no" ]]; then
    warn ".env not found on Pi -- copying from local"
    scp "${LOCAL_DIR}/.env" "${PI_TARGET}:${REMOTE_DIR}/.env"
    warn ">>> Edit ${REMOTE_DIR}/.env on the Pi if any values differ <<<"
else
    info ".env already on Pi -- skipping (won't overwrite)"
fi

# ---------------------------------------------------------------------------
# 3. Create venv & install Python deps
# ---------------------------------------------------------------------------
info "Installing Python dependencies on Pi..."

ssh "${PI_TARGET}" bash <<REMOTE_DEPS
set -euo pipefail
cd "${REMOTE_DIR}"

mkdir -p data/conversations data/uber_browser_profile

if [ ! -d "${VENV_DIR}" ]; then
    echo "[Pi] Creating virtualenv..."
    python3 -m venv "${VENV_DIR}"
fi

echo "[Pi] pip install..."
"${PIP}" install --upgrade pip -q 2>&1 | tail -1
"${PIP}" install -r requirements.txt -q 2>&1 | tail -1

if "${PYTHON}" -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
    echo "[Pi] Playwright already installed"
else
    echo "[Pi] Installing Playwright chromium..."
    "${PYTHON}" -m playwright install --with-deps chromium 2>&1 | tail -5 || \
        echo "[Pi] Playwright install needs manual attention (run: ${PYTHON} -m playwright install chromium)"
fi

echo "[Pi] Dependencies ready"
REMOTE_DEPS

ok "Dependencies installed"

# ---------------------------------------------------------------------------
# 4. Generate systemd unit files locally, upload, and enable
# ---------------------------------------------------------------------------
info "Provisioning systemd services..."

TMPDIR_LOCAL=$(mktemp -d)
trap 'rm -rf "${TMPDIR_LOCAL}"' EXIT

# -- ngrok tunnel --
cat > "${TMPDIR_LOCAL}/voiceassistant-ngrok.service" <<EOF
[Unit]
Description=VoiceAssistant ngrok tunnel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${PI_USER}
ExecStartPre=/bin/sleep 5
ExecStart=${NGROK_BIN} http --domain=${NGROK_DOMAIN} 8765
Restart=on-failure
RestartSec=10
StandardOutput=append:${REMOTE_DIR}/ngrok.log
StandardError=append:${REMOTE_DIR}/ngrok.log

[Install]
WantedBy=multi-user.target
EOF

# -- main server (SMS + WebSocket, port 8765) --
cat > "${TMPDIR_LOCAL}/voiceassistant-server.service" <<EOF
[Unit]
Description=VoiceAssistant main server (SMS/WebSocket)
After=network-online.target voiceassistant-ngrok.service
Wants=network-online.target

[Service]
Type=simple
User=${PI_USER}
WorkingDirectory=${REMOTE_DIR}
EnvironmentFile=${REMOTE_DIR}/.env
ExecStart=${PYTHON} ${REMOTE_DIR}/server.py
Restart=on-failure
RestartSec=5
StandardOutput=append:${REMOTE_DIR}/server.log
StandardError=append:${REMOTE_DIR}/server.log

[Install]
WantedBy=multi-user.target
EOF

# -- web control panel (port 8000) --
cat > "${TMPDIR_LOCAL}/voiceassistant-webserver.service" <<EOF
[Unit]
Description=VoiceAssistant web control panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${PI_USER}
WorkingDirectory=${REMOTE_DIR}
EnvironmentFile=${REMOTE_DIR}/.env
ExecStart=${PYTHON} ${REMOTE_DIR}/web_server.py
Restart=on-failure
RestartSec=5
StandardOutput=append:${REMOTE_DIR}/webserver.log
StandardError=append:${REMOTE_DIR}/webserver.log

[Install]
WantedBy=multi-user.target
EOF

scp -q "${TMPDIR_LOCAL}"/*.service "${PI_TARGET}:/tmp/"

ssh "${PI_TARGET}" bash <<'ENABLE'
set -euo pipefail
sudo mv /tmp/voiceassistant-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable voiceassistant-ngrok.service
sudo systemctl enable voiceassistant-server.service
sudo systemctl enable voiceassistant-webserver.service
echo "[Pi] Services enabled"
ENABLE

ok "Systemd services provisioned"

# ---------------------------------------------------------------------------
# 5. Restart everything
# ---------------------------------------------------------------------------
info "Restarting services..."

ssh "${PI_TARGET}" bash <<'RESTART'
set -euo pipefail

sudo systemctl restart voiceassistant-ngrok.service
sleep 3
sudo systemctl restart voiceassistant-server.service
sudo systemctl restart voiceassistant-webserver.service
sleep 2

echo ""
echo "=== Service Status ==="
for svc in voiceassistant-ngrok voiceassistant-server voiceassistant-webserver; do
    STATUS=$(systemctl is-active "$svc" 2>/dev/null || true)
    if [ "$STATUS" = "active" ]; then
        echo "  $svc : active"
    else
        echo "  $svc : $STATUS  <-- check with: journalctl -u $svc -n 20"
    fi
done
echo ""
RESTART

ok "Services restarted"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Deploy complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Services:"
echo "    voiceassistant-ngrok     -> ngrok tunnel (${NGROK_DOMAIN})"
echo "    voiceassistant-server    -> server.py     :8765"
echo "    voiceassistant-webserver -> web_server.py :8000"
echo ""
echo "  Useful commands (SSH to Pi first):"
echo "    sudo systemctl status  voiceassistant-server"
echo "    sudo journalctl -u voiceassistant-server -f"
echo "    sudo systemctl restart voiceassistant-server"
echo "    tail -f ${REMOTE_DIR}/server.log"
echo ""
