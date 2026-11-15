#!/usr/bin/env bash
# Sunucuda bir NEXORA aracını doğru kullanıcı ve anahtarlarla çalıştırır:
#   sudo bash /opt/nexora/deploy/calistir.sh cuzdan_kesif.py
# Yalnızca aşağıdaki salt okunur rapor/analiz araçlarına izin verilir.
set -euo pipefail
IZINLI="cuzdan_kesif.py cuzdan_analiz.py cuzdan_tarama.py takip_kaybi.py golge_rapor.py gunluk_rapor.py zarar_kesme.py token_filtre.py yedek.py"
ARAC="${1:-}"; shift || true
case " $IZINLI " in *" $ARAC "*) ;; *) echo "Kullanım: sudo bash /opt/nexora/deploy/calistir.sh ARAÇ [argüman]"; echo "Araçlar: $IZINLI"; exit 1;; esac
[ "$(id -u)" -eq 0 ] || { echo "sudo ile çalıştırın"; exit 1; }
exec sudo -u nexora bash -c 'set -a; . /etc/nexora.env; set +a; cd /opt/nexora/backend && exec python3 -u "$@"' _ "$ARAC" "$@"
