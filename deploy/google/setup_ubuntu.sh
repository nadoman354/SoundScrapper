#!/usr/bin/env bash
set -Eeuo pipefail

APP_USER="soundscrapper"
APP_GROUP="soundscrapper"
APP_ROOT="/opt/soundscrapper"
APP_DIR="${APP_ROOT}/app"
DATA_DIR="/var/lib/soundscrapper"
ENV_FILE="${APP_ROOT}/.env"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run with sudo: sudo bash deploy/google/setup_ubuntu.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y \
    curl \
    nginx \
    python3 \
    python3-pip \
    python3-venv \
    rsync

if ! getent group "${APP_GROUP}" >/dev/null; then
    groupadd --system "${APP_GROUP}"
fi

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    useradd \
        --system \
        --gid "${APP_GROUP}" \
        --home-dir "${APP_ROOT}" \
        --shell /usr/sbin/nologin \
        "${APP_USER}"
fi

install -d -m 0755 "${APP_ROOT}" "${APP_DIR}"
install -d -m 0750 -o "${APP_USER}" -g "${APP_GROUP}" "${DATA_DIR}" "${DATA_DIR}/previews"

REPO_REAL="$(realpath "${REPO_DIR}")"
APP_REAL="$(realpath -m "${APP_DIR}")"

if [[ "${REPO_REAL}" != "${APP_REAL}" ]]; then
    rsync -a --delete \
        --exclude ".cache" \
        --exclude ".env" \
        --exclude ".git" \
        --exclude ".pytest_cache" \
        --exclude ".venv" \
        --exclude "__pycache__" \
        --exclude "*.db" \
        "${REPO_DIR}/" \
        "${APP_DIR}/"
fi

python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip
"${APP_DIR}/.venv/bin/python" -m pip install -e "${APP_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
    install -m 0640 -o root -g "${APP_GROUP}" \
        "${SCRIPT_DIR}/soundscrapper.env.example" \
        "${ENV_FILE}"
else
    chown root:"${APP_GROUP}" "${ENV_FILE}"
    chmod 0640 "${ENV_FILE}"
fi

chown -R root:root "${APP_DIR}"
chown -R "${APP_USER}:${APP_GROUP}" "${DATA_DIR}"

install -m 0644 "${SCRIPT_DIR}/soundscrapper.service" /etc/systemd/system/soundscrapper.service
install -m 0644 "${SCRIPT_DIR}/nginx.conf" /etc/nginx/sites-available/soundscrapper
ln -sfn /etc/nginx/sites-available/soundscrapper /etc/nginx/sites-enabled/soundscrapper
rm -f /etc/nginx/sites-enabled/default

systemctl daemon-reload
systemctl enable --now soundscrapper
nginx -t
systemctl enable --now nginx
systemctl reload nginx

echo "SoundScrapper installed."
echo "Edit ${ENV_FILE}, set FREESOUND_API_KEY, then run:"
echo "  sudo systemctl restart soundscrapper"
echo "Health check:"
echo "  curl http://127.0.0.1:8000/health"
