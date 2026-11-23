"""EVM 'çözülemeyen işlem' teşhisi (N24/N25, salt okunur): cüzdan analizinde swap olarak çözülemeyen işlemlerin NEDENİ.
  python3 evm_teshis.py base                  # evm_analiz_base.json'da en çok çözülemeyeni olan 4 cüzdan
  python3 evm_teshis.py bnb 0xabc... 0xdef...  # belirli cüzdanlar
Her işlem bir sınıfa ayrılır; iki token değişen işlemlerde en sık görülen token'lar yazılır (karşı varlık listesine
eklenmesi gereken bir ödeme token'ı var mı?). İşlem gönderilmez, anahtar kullanılmaz."""
from nexora.dosya import json_oku, metin_oku, bayt_oku
import json, os, sys
from collections import Counter, defaultdict
import requests
from nexora.evm import ZINCIRLER, EvmRpc, EvmHatasi, gezgin_islemleri, coz_tam, yerel_fark, TRANSFER, _adr
from nexora import evm_analiz as A

GUN = int(os.getenv("EVM_ANALIZ_GUN", "5"))


def neden(tx, makbuz, cuzdan, zincir):
    """Çözülemeyen işlemin sınıfı ve ilgili token'lar: (sınıf, [token])."""
    if not isinstance(makbuz, dict) or makbuz.get("status") not in ("0x1", 1): return "başarısız işlem", []
    w = cuzdan.lower(); karsi = ZINCIRLER[zincir]["karsi"]; d = {}
    for l in makbuz.get("logs") or []:
        t = l.get("topics") or []
        if not t or t[0] != TRANSFER or len(t) != 3: continue
        a = (l.get("address") or "").lower(); v = int(l.get("data") or "0x0", 16)
        if _adr(t[2]) == w: d[a] = d.get(a, 0) + v
        if _adr(t[1]) == w: d[a] = d.get(a, 0) - v
    tok = [a for a, v in d.items() if v and a not in karsi]
    gelen = [a for a in tok if d[a] > 0]; giden = [a for a in tok if d[a] < 0]
    kendi = (tx.get("from") or "").lower() == w
    if len(tok) >= 2:
        return ("token→token takas (iki token, karşı varlık yok)" if gelen and giden else "birden çok token aynı yönde"), tok
    if len(tok) == 1 and not kendi: return ("başkasının gönderdiği gelen token (airdrop/ödül/transfer)" if gelen else "başkasının başlattığı giden token"), tok
    if len(tok) == 1: return ("kendi gönderdiği token (transfer, karşılık yok)" if giden else "kendi işlemiyle gelen token, karşılık görünmüyor"), tok
    if not tok and d: return "yalnızca karşı varlık hareketi (ETH/WETH/stable)", []
    return "token hareketi yok (makbuzda Transfer olayı yok)", []


def main(argv, rpc=None, s=None):
    z = argv[0] if argv else "base"
    if z not in ZINCIRLER: sys.exit("zincir: bnb ya da base")
    c = ZINCIRLER[z]; rpc = rpc or EvmRpc(os.getenv(c["rpc_env"]) or c["rpc"]); s = s or requests.Session()
    cuzdanlar = [a.lower() for a in argv[1:]]
    if not cuzdanlar:
        try: kayit = json_oku(f"evm_analiz_{z}.json")
        except (OSError, ValueError): sys.exit(f"evm_analiz_{z}.json yok: önce evm_kesif.py {z} çalıştırın ya da cüzdan verin")
        kayit = sorted((m for m in kayit if m.get("cozulemeyen")), key=lambda m: -m["cozulemeyen"])
        cuzdanlar = [m["wallet"] for m in kayit[:4]]
    if not cuzdanlar: sys.exit("Çözülemeyen işlemi olan cüzdan yok.")
    son = rpc.blok(); bas = son - int(GUN * 86400 / A.BLOK_SURESI[z])
    genel, tokenler = Counter(), Counter(); ornek = defaultdict(list)
    for w in cuzdanlar:
        islemler = gezgin_islemleri(s, z, w, bas) if c.get("gezgin") else None
        if islemler is None and c.get("gezgin"):
            print(f"\n{w[:6]}…{w[-4:]}: gezgin yanıt vermedi, atlandı", flush=True); continue
        if islemler is None:
            islemler = {}
            try:
                for konular in ([TRANSFER, None, "0x" + "0" * 24 + w[2:]], [TRANSFER, "0x" + "0" * 24 + w[2:]]):
                    for l in rpc.call("eth_getLogs", [{"fromBlock": hex(bas), "toBlock": hex(son), "topics": konular}]) or []:
                        islemler.setdefault(l["transactionHash"], int(l["blockNumber"], 16))
            except EvmHatasi as e:
                print(f"\n{w[:6]}…{w[-4:]}: geçmiş okunamadı ({str(e)[:60]}), atlandı", flush=True); continue
        sinif = Counter(); cozulen = 0
        for karma, blok in sorted(islemler.items(), key=lambda x: x[1])[-150:]:
            try:
                tx = rpc.call("eth_getTransactionByHash", [karma]) or {}; mk = rpc.call("eth_getTransactionReceipt", [karma]) or {}
            except EvmHatasi:
                sinif["okunamadı"] += 1; continue
            if coz_tam(rpc, tx, mk, w, z, blok): cozulen += 1; continue
            n, tk = neden(tx, mk, w, z); sinif[n] += 1; genel[n] += 1; tokenler.update(tk)
            if len(ornek[n]) < 2:                            # her sınıftan örnek: işlem karması, ETH değeri, yerel bakiye farkı
                ornek[n].append(f"{karma}  değer {int(tx.get('value') or '0x0', 16) / 1e18:.5f} ETH  "
                                f"bakiye farkı {(lambda f: 'okunamadı' if f is None else f'{f / 1e18:+.5f} ETH')(yerel_fark(rpc, w, blok, tx, mk))}  "
                                f"hedef {(tx.get('to') or '')[:10]}  olay {len(mk.get('logs') or [])}")
        print(f"\n{w[:6]}…{w[-4:]}: {len(islemler)} işlem, {cozulen} swap çözüldü", flush=True)
        for n, k in sinif.most_common(): print(f"  {k:>4}  {n}")
    print("\n== TOPLAM çözülemeyen ==")
    for n, k in genel.most_common(): print(f"  {k:>4}  {n}")
    if tokenler:
        print("En sık görülen token'lar (karşı varlık olabilir mi?):")
        for t, k in tokenler.most_common(6): print(f"  {k:>4}  {t}")
    print("Örnek işlemler:")
    for n, ler in ornek.items():
        print(f"  [{n}]")
        for o in ler: print(f"    {o}")


if __name__ == "__main__":
    main(sys.argv[1:])
