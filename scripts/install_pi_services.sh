#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/harrison/student_search_backend"
SYSTEMD_DIR="/etc/systemd/system"
NGINX_CONFIG="${REPO_DIR}/nginx_unix.conf"

APP_SERVICES=(
  "student-search-backend.service"
  "student-search-frontend.service"
)

ALL_SERVICES=(
  "student-search-backend.service"
  "student-search-frontend.service"
  "student-search-nginx.service"
)

echo "Installing systemd unit files..."
for service in "${ALL_SERVICES[@]}"; do
  sudo cp "${REPO_DIR}/deploy/systemd/${service}" "${SYSTEMD_DIR}/${service}"
done

echo "Reloading systemd..."
sudo systemctl daemon-reload

echo "Validating nginx config..."
sudo /usr/sbin/nginx -t -c "${NGINX_CONFIG}"

if systemctl list-unit-files | grep -q "^nginx.service"; then
  if sudo systemctl is-active --quiet nginx; then
    echo "Stopping default nginx.service to avoid port conflicts..."
    sudo systemctl stop nginx
  fi
  if sudo systemctl is-enabled --quiet nginx; then
    echo "Disabling default nginx.service..."
    sudo systemctl disable nginx
  fi
fi

echo "Enabling and starting services..."
for service in "${APP_SERVICES[@]}"; do
  sudo systemctl enable --now "${service}"
done
sudo systemctl enable --now student-search-nginx.service

echo
echo "Service status:"
for service in "${ALL_SERVICES[@]}"; do
  echo "----- ${service} -----"
  sudo systemctl --no-pager --full status "${service}" | head -n 20 || true
done
