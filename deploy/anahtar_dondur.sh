#!/usr/bin/env bash
# NEXORA sunucu API anahtarını (NEXORA_API_KEY) yeniler (N35).
#   sudo bash /opt/nexora/deploy/anahtar_dondur.sh
# Yeni anahtar /etc/nexora.env'e yazılır, eski dosya /etc/nexora.env.yedek olarak saklanır, sunucu yeniden başlar.
# Yeni anahtar YALNIZCA bir kez ekrana yazılır: uygulamada Profil → Sunucu bağlantısı → API anahtarı alanına girin,
# sonra ekranı temizleyin (clear). Anahtarı kimseyle paylaşmayın, ekran görüntüsünü göndermeyin.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "sudo ile çalıştırın"; exit 1; }
ENV=/etc/nexora.env
[ -f "$ENV" ] || { echo "$ENV yok"; exit 1; }
YENI="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
cp -p "$ENV" "$ENV.yedek"   # izin ve sahiplik korunur (araçlar dosyayı okuyabilmeli)
if grep -q '^NEXORA_API_KEY=' "$ENV"; then
  python3 - "$ENV" "$YENI" <<'PY'
import sys
yol, yeni = sys.argv[1], sys.argv[2]
satirlar = open(yol).read().splitlines()
open(yol, "w").write("\n".join(("NEXORA_API_KEY=" + yeni) if s.startswith("NEXORA_API_KEY=") else s for s in satirlar) + "\n")
PY
else
  printf 'NEXORA_API_KEY=%s\n' "$YENI" >> "$ENV"
fi
systemctl restart nexora-sunucu
echo "Anahtar yenilendi. Eski anahtar artık çalışmaz."
echo
echo "YENİ ANAHTAR (bir kez gösterilir, uygulamaya girin, sonra 'clear' yazın):"
echo "$YENI"
