#!/usr/bin/env bash
# Ręczne uruchomienie bota z tymi samymi kluczami i ograniczeniami co usługa.
# Klucze są czytane przez systemd z /etc/prognozy/prognozy.env, nie trafiają
# do wiersza poleceń ani do historii powłoki.
#   sudo bash /opt/prognozy/deploy/run-once.sh check
#   sudo bash /opt/prognozy/deploy/run-once.sh run --mode test --dry-run
#   sudo bash /opt/prognozy/deploy/run-once.sh run --mode minibench --publish
set -euo pipefail
exec systemd-run --quiet --pty --wait --collect \
  --uid=prognozy --gid=prognozy \
  -p EnvironmentFile=/etc/prognozy/prognozy.env \
  -p StateDirectory=prognozy \
  -p WorkingDirectory=/var/lib/prognozy \
  -E PROGNOZY_STATE_DIR=/var/lib/prognozy \
  -E HOME=/var/lib/prognozy \
  -E PYTHONUNBUFFERED=1 \
  /opt/prognozy/.venv/bin/prognozy "$@"
