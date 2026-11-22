#!/usr/bin/env bash
# Sunucuda bir NEXORA aracını doğru kullanıcı ve anahtarlarla çalıştırır:
#   sudo bash /opt/nexora/deploy/calistir.sh cuzdan_kesif.py
#   sudo bash /opt/nexora/deploy/calistir.sh cuzdan_kesif.py KESIF_TOKEN=40      (sayısal ayar verilebilir)
# Yalnızca aşağıdaki araçlara izin verilir. cuzdan_ekle.py --uygula dışındakiler salt okunur rapor/analizdir.
set -euo pipefail
IZINLI="bildirim_tara.py borsa_ortusme.py kanit_raporu.py yonlendirici.py evm_kesif.py evm_dene.py borsa_liste.py borsa_kesif.py borsa_ortusme.py yz_filtre.py pilot_cuzdan.py pilot_olcum.py emir_dene.py otomatik_kesif.py cuzdan_kesif.py cuzdan_analiz.py cuzdan_ekle.py hesap_denetim.py cuzdan_tarama.py takip_kaybi.py golge_rapor.py gunluk_rapor.py zarar_kesme.py token_filtre.py yedek.py yz_veri.py yz_model.py portfoy_denetim.py"
AYARLAR="KESIF_PIYASA KESIF_PIYASA_SAAT KESIF_TOKEN KESIF_LIMIT KESIF_SAYFA KESIF_MIN_TUTMA_SN KESIF_PENCERE_SN KESIF_EN_AZ ANALIZ_LIMIT ANALIZ_HEPSI EKLE_EN_FAZLA PILOT_N PILOT_USD ORTUSME_GUN BORSA_KESIF_TOKEN BORSA_KESIF_SAAT BORSA_KESIF_EN_AZ EVM_KESIF_TOKEN EVM_KESIF_EN_AZ EVM_ANALIZ_ADAY EVM_ANALIZ_GUN"
ARAC="${1:-}"; shift || true
case " $IZINLI " in *" $ARAC "*) ;; *) echo "Kullanım: sudo bash /opt/nexora/deploy/calistir.sh ARAÇ [AYAR=sayı] [argüman]"; echo "Araçlar: $IZINLI"; exit 1;; esac
[ "$(id -u)" -eq 0 ] || { echo "sudo ile çalıştırın"; exit 1; }
ENV=()
while [ $# -gt 0 ] && [[ "$1" == *=* ]]; do
  AD="${1%%=*}"; DEGER="${1#*=}"
  case " $AYARLAR " in *" $AD "*) ;; *) echo "İzin verilmeyen ayar: $AD (izinli: $AYARLAR)"; exit 1;; esac
  [[ "$DEGER" =~ ^[0-9]{1,6}$ ]] || { echo "$AD sayı olmalı"; exit 1; }
  ENV+=("$AD=$DEGER"); shift
done
exec sudo -u nexora env "${ENV[@]}" bash -c 'set -a; . /etc/nexora.env; set +a; cd /opt/nexora/backend && exec python3 -u "$@"' _ "$ARAC" "$@"
