#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/weatheredgeflow}"
REPO_URL="${REPO_URL:-}"

echo "WeatherEdgeflow Oracle Free Tier setup"
echo "Target directory: ${APP_DIR}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root or with sudo: sudo bash deploy/oracle_free_tier_setup.sh"
  exit 1
fi

apt-get update
apt-get install -y ca-certificates curl git ufw

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker

if [[ ! -d "${APP_DIR}/.git" ]]; then
  if [[ -z "${REPO_URL}" ]]; then
    echo "Set REPO_URL before first VPS install, for example:"
    echo "REPO_URL=https://github.com/YOUR_USER/weatheredgeflow.git sudo -E bash deploy/oracle_free_tier_setup.sh"
    exit 1
  fi
  mkdir -p "$(dirname "${APP_DIR}")"
  git clone "${REPO_URL}" "${APP_DIR}"
fi

cd "${APP_DIR}"
git pull --ff-only || true

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

mkdir -p data logs
docker compose up -d --build

ufw allow OpenSSH
ufw allow 8000/tcp
ufw --force enable

echo "Done."
echo "Dashboard: http://SERVER_IP:8000"
echo "Logs: docker compose logs -f"
