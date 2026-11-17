#!/usr/bin/env bash
# Instalacja / aktualizacja bota Prognozy na VPS (Debian/Ubuntu z systemd).
# Uruchom jako root z katalogu sklonowanego repozytorium:
#   sudo bash deploy/install.sh
# Skrypt dotyka tylko: użytkownika "prognozy", /opt/prognozy, /etc/prognozy,
# /var/lib/prognozy oraz jednostek prognozy.service/.timer. Nic poza tym.
set -euo pipefail

APP_DIR=/opt/prognozy
ETC_DIR=/etc/prognozy
ENV_FILE=$ETC_DIR/prognozy.env
SRC_DIR=$(cd "$(dirname "$0")/.." && pwd)

if [[ $EUID -ne 0 ]]; then
  echo "Uruchom jako root (sudo)." >&2
  exit 1
fi

# 1. Osobny użytkownik systemowy bez powłoki i bez katalogu domowego.
if ! id prognozy >/dev/null 2>&1; then
  useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin prognozy
fi

# 2. Kod w /opt/prognozy (kopia, bez .git i bez lokalnego stanu).
install -d -o root -g root -m 0755 "$APP_DIR"
tar -C "$SRC_DIR" --exclude=.git --exclude=.venv --exclude=stan --exclude='*.env' -cf - . \
  | tar -C "$APP_DIR" -xf -

# 3. Środowisko Pythona (3.11–3.13). Najpierw uv, jeśli jest; inaczej systemowy python3.
cd "$APP_DIR"
if command -v uv >/dev/null 2>&1; then
  uv venv --python 3.12 --allow-existing .venv
  uv pip install --python .venv/bin/python --reinstall-package prognozy .
else
  PY=${PYTHON:-python3}
  "$PY" - <<'EOF'
import sys
if not ((3, 11) <= sys.version_info[:2] <= (3, 13)):
    sys.exit(f"Potrzebny Python 3.11-3.13, jest {sys.version.split()[0]}. Zainstaluj uv albo ustaw PYTHON=...")
EOF
  "$PY" -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet --force-reinstall --no-deps . && .venv/bin/pip install --quiet .
fi

# 4. Plik z kluczami (tworzony tylko raz; potem edytujesz go ręcznie).
install -d -o root -g root -m 0755 "$ETC_DIR"
if [[ ! -f $ENV_FILE ]]; then
  install -o root -g root -m 0600 "$APP_DIR/deploy/prognozy.env.example" "$ENV_FILE"
  echo "Utworzono $ENV_FILE: wpisz klucze (nano $ENV_FILE)."
fi
chmod 0600 "$ENV_FILE"

# 5. Jednostki systemd.
install -o root -g root -m 0644 "$APP_DIR/deploy/prognozy.service" /etc/systemd/system/prognozy.service
install -o root -g root -m 0644 "$APP_DIR/deploy/prognozy.timer" /etc/systemd/system/prognozy.timer
systemctl daemon-reload

echo
echo "Gotowe. Dalej:"
echo "  1) nano $ENV_FILE                     # wpisz klucze"
echo "  2) sudo bash $APP_DIR/deploy/run-once.sh check        # sprawdzenie konfiguracji"
echo "  3) sudo bash $APP_DIR/deploy/run-once.sh run --mode test --dry-run"
echo "  4) systemctl enable --now prognozy.timer"
echo "Logi: journalctl -u prognozy -f"
