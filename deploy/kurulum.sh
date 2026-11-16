#!/usr/bin/env bash
# NEXORA bulut sunucu kurulumu (N13). Ubuntu/Debian, root olarak: sudo bash deploy/kurulum.sh
# Yaptıkları: python3 + requests kurar, 'nexora' kullanıcısı açar, kodu /opt/nexora'ya koyar,
# anahtarları /etc/nexora.env'e (yalnızca root ve nexora okuyabilir) yazar, servisleri ve gece yedeğini açar.
# Dışarıya port AÇMAZ: sunucu yalnızca Tailscale özel ağ adresinden dinler.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "root olarak çalıştırın: sudo bash deploy/kurulum.sh"; exit 1; }
KAYNAK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HEDEF=/opt/nexora

apt-get update -qq && apt-get install -y -qq python3 python3-requests git >/dev/null
id nexora >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin nexora
if [ "$KAYNAK" != "$HEDEF" ]; then
  mkdir -p "$HEDEF"; cp -a "$KAYNAK"/. "$HEDEF"/
fi
chown -R nexora:nexora "$HEDEF"

TS_IP="$(command -v tailscale >/dev/null && tailscale ip -4 2>/dev/null | head -1 || true)"
if [ -z "$TS_IP" ]; then
  echo "Tailscale bulunamadı. Önce kurun ve giriş yapın:"
  echo "  curl -fsSL https://tailscale.com/install.sh | sh && tailscale up"
  echo "Sonra bu betiği yeniden çalıştırın."; exit 1
fi

if [ ! -f /etc/nexora.env ]; then
  echo "Anahtarlar /etc/nexora.env dosyasına yazılacak (ekranda görünmez)."
  read -r -s -p "HELIUS_API_KEY: " H; echo
  read -r -s -p "JUPITER_API_KEY (yoksa boş): " J; echo
  K="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  umask 077
  printf "HELIUS_API_KEY=%s\nJUPITER_API_KEY=%s\nNEXORA_API_KEY=%s\nNEXORA_HOST=%s\n" "$H" "$J" "$K" "$TS_IP" > /etc/nexora.env
  chown root:nexora /etc/nexora.env; chmod 640 /etc/nexora.env
  echo "Uygulama için yeni sunucu anahtarı üretildi; görmek için: sudo grep NEXORA_API_KEY /etc/nexora.env"
fi

install -m 644 "$HEDEF"/deploy/nexora-*.service "$HEDEF"/deploy/nexora-*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now nexora-sunucu nexora-takip nexora-yedek.timer nexora-kesif.timer
sleep 3
systemctl --no-pager --lines=0 status nexora-sunucu nexora-takip 2>/dev/null | grep -E "●|Active" || true
[ -f "$HEDEF/backend/wallets.txt" ] || echo "Not: wallets.txt yok; takip, telefondaki yedek geri yüklenene kadar yeniden denemeye devam eder (normal)."
echo
echo "Uygulamada sunucu adresi: http://$TS_IP:8000  (telefonda Tailscale açık olmalı)"
echo "Günlük: journalctl -u nexora-takip -f      Yedekler: $HEDEF/backend/yedekler"
