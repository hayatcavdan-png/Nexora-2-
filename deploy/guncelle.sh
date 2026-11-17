#!/usr/bin/env bash
# NEXORA sunucu güncellemesi: sudo bash /opt/nexora/deploy/guncelle.sh
# Kodu çeker, testleri çalıştırır; testler GEÇMEZSE eski sürüme döner ve servislere dokunmaz.
# Son başarıyla kurulan sürüm .kurulan dosyasında tutulur: önceki çalıştırma yarıda kaldıysa (bağlantı koptu, CTRL+C)
# kod zaten çekilmiş olsa bile testler ve yeniden başlatma bu sefer tamamlanır.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "root olarak çalıştırın: sudo bash /opt/nexora/deploy/guncelle.sh"; exit 1; }
cd /opt/nexora
ONCE="$(sudo -u nexora git rev-parse HEAD)"
sudo -u nexora git pull --ff-only -q
SONRA="$(sudo -u nexora git rev-parse HEAD)"
KURULAN="$(cat /opt/nexora/.kurulan 2>/dev/null || true)"
if [ "$ONCE" = "$SONRA" ] && [ "$KURULAN" = "$SONRA" ]; then echo "Zaten güncel ($(sudo -u nexora git log -1 --format=%s))."; exit 0; fi
[ -n "$KURULAN" ] && [ "$ONCE" = "$SONRA" ] && ONCE="$KURULAN"   # yarım kalan kurulum: başarısızsa son kurulan sürüme dön
echo "Yeni sürüm: $(sudo -u nexora git log -1 --format=%s)"
if ! (cd backend && sudo -u nexora python3 -m unittest discover -s tests -q 2>&1 | tail -3); then
  echo "Testler GEÇMEDİ: eski sürüme dönülüyor, servisler değişmedi."
  sudo -u nexora git reset -q --hard "$ONCE"; exit 1
fi
install -m 644 deploy/nexora-*.service deploy/nexora-*.timer /etc/systemd/system/
systemctl daemon-reload
for T in deploy/nexora-*.timer; do systemctl enable --now -q "$(basename "$T")"; done
systemctl enable -q nexora-piyasa nexora-bnb nexora-base 2>/dev/null || true
systemctl restart nexora-sunucu nexora-takip nexora-piyasa nexora-bnb nexora-base
sleep 5
systemctl --no-pager --lines=0 status nexora-sunucu nexora-takip nexora-piyasa nexora-bnb nexora-base 2>/dev/null | grep -E "●|Active" || true
journalctl -u nexora-takip -n 3 --no-pager -o cat || true
echo "$SONRA" > /opt/nexora/.kurulan
