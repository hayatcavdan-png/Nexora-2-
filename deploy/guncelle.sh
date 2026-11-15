#!/usr/bin/env bash
# NEXORA sunucu güncellemesi: sudo bash /opt/nexora/deploy/guncelle.sh
# Kodu çeker, testleri çalıştırır; testler GEÇMEZSE eski sürüme döner ve servislere dokunmaz.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "root olarak çalıştırın: sudo bash /opt/nexora/deploy/guncelle.sh"; exit 1; }
cd /opt/nexora
ONCE="$(sudo -u nexora git rev-parse HEAD)"
sudo -u nexora git pull --ff-only -q
SONRA="$(sudo -u nexora git rev-parse HEAD)"
if [ "$ONCE" = "$SONRA" ]; then echo "Zaten güncel ($(git log -1 --format=%s))."; exit 0; fi
echo "Yeni sürüm: $(git log -1 --format=%s)"
if ! (cd backend && sudo -u nexora python3 -m unittest discover -s tests -q 2>&1 | tail -3); then
  echo "Testler GEÇMEDİ: eski sürüme dönülüyor, servisler değişmedi."
  sudo -u nexora git reset -q --hard "$ONCE"; exit 1
fi
install -m 644 deploy/nexora-*.service deploy/nexora-yedek.timer /etc/systemd/system/
systemctl daemon-reload
systemctl restart nexora-sunucu nexora-takip
sleep 5
systemctl --no-pager --lines=0 status nexora-sunucu nexora-takip 2>/dev/null | grep -E "●|Active" || true
journalctl -u nexora-takip -n 3 --no-pager -o cat || true
