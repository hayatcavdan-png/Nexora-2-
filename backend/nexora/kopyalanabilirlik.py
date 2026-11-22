"""Geliştirme 1 (PROFIT ENGINE V1): cüzdan kopyalanabilirlik puanı ve A/B/C sınıflandırması.

SALT RAPOR. Bu modül kadro kararlarını DEĞİŞTİRMEZ; yalnızca mevcut ölçümlerden (kadro.olcum: NEXORA'nın kendi
simüle ettiği net kopyalama getirisi, 'kaynak' ufku) bir puan ve sınıf üretir. Varsayılan KOPYA_SKOR_MOD=kapali
ise hiçbir yerde kullanılmaz; yalnızca `python3 -m nexora.kopyalanabilirlik` ile elle raporlanır.

Sınıflar:
  A — kopyalamaya uygun: yeterli ileri dönem kanıtı, pozitif net getiri, makul düşüş, tek tokene bağımlı değil.
  B — gölge izleme: veri henüz yetersiz ya da kriterlerin bir kısmı eksik.
  C — riskli / olumsuz: maliyet sonrası negatif, aşırı düşüş, bot şüphesi veya tek token bağımlılığı.

Bilinen sınırlar (raporda da yazılır): kaynak ufku geçmiş ölçümdür; A sınıfı bir cüzdanın gelecekte de kâr
edeceğinin garantisi değildir. Maksimum düşüş ve bot/tek-token ek verileri yalnızca çağıran tarafından verilirse
kullanılır; verilmezse ilgili kriter 'veri yok' sayılıp A'yı engellemez ama puanı da artırmaz.
"""
import os

KANIT_N = 15            # A için en az ölçüm
ZARAR_N = 8             # C için olumsuz ortalama için en az ölçüm (kadro.DUSUR_N ile uyumlu)
A_ORT = 3.0             # A için net ortalama getiri (%) — kadro.TERFI_ORT ile aynı eşik
A_POZITIF = 0.5         # A için kazanan oran
MAKS_DUSUS_A = -40.0    # A için kabul edilebilir en kötü düşüş (%)
MAKS_DUSUS_C = -60.0    # bu seviyenin altı C
TEK_TOKEN_C = 0.6       # işlemlerin bu oranı tek token ise C
MOD = os.getenv("KOPYA_SKOR_MOD", "kapali")          # kapali | rapor


def puan(m, ek=None):
    """0-100 arası puan. m: kadro.olcum sözlüğü (n, ort, medyan, pozitif). ek: isteğe bağlı maks_dusus, tek_token_pay, bot_suphe."""
    ek = ek or {}
    if not m or m.get("n", 0) == 0:
        return 0.0
    n = m["n"]
    guven = min(1.0, n / KANIT_N)                                   # az ölçüm puanı düşürür
    ort = max(-10.0, min(10.0, m["ort"])) / 10.0                    # -1 .. 1
    med = 1.0 if m["medyan"] > 0 else 0.0
    poz = m["pozitif"]
    ham = 50 + 40 * ort * guven + 10 * (poz - 0.5) * 2 * guven       # 0..100 civarı
    ham += 5 * med * guven
    dd = ek.get("maks_dusus")
    if dd is not None and dd < MAKS_DUSUS_A: ham -= 15
    if ek.get("tek_token_pay", 0) >= TEK_TOKEN_C: ham -= 15
    if ek.get("bot_suphe"): ham -= 25
    return round(max(0.0, min(100.0, ham)), 1)


def sinif(m, ek=None):
    """'A' | 'B' | 'C' ve gerekçe listesi."""
    ek = ek or {}
    if not m or m.get("n", 0) == 0:
        return "B", ["henüz ölçüm yok"]
    n, ort, med, poz = m["n"], m["ort"], m["medyan"], m["pozitif"]
    neden = []
    dd = ek.get("maks_dusus")
    if ek.get("bot_suphe"): return "C", ["bot şüphesi"]
    if ek.get("tek_token_pay", 0) >= TEK_TOKEN_C: return "C", [f"işlemlerin %{ek['tek_token_pay'] * 100:.0f}'i tek token"]
    if dd is not None and dd < MAKS_DUSUS_C: return "C", [f"maks düşüş %{dd:.0f}"]
    if n >= ZARAR_N and ort < 0: return "C", [f"maliyet sonrası ortalama %{ort:+.2f} ({n} ölçüm)"]
    if n >= KANIT_N and ort >= A_ORT and med > 0 and poz >= A_POZITIF:
        if dd is not None and dd < MAKS_DUSUS_A:
            return "B", [f"ortalama iyi ama maks düşüş %{dd:.0f}"]
        return "A", [f"{n} ölçüm, ortalama %{ort:+.2f}, medyan %{med:+.2f}, kazanan %{poz * 100:.0f}"]
    if n < KANIT_N: neden.append(f"yetersiz ölçüm ({n}/{KANIT_N})")
    if ort < A_ORT: neden.append(f"ortalama %{ort:+.2f} (A için ≥{A_ORT})")
    if med <= 0: neden.append("medyan ≤ 0")
    if poz < A_POZITIF: neden.append(f"kazanan oran %{poz * 100:.0f}")
    return "B", neden or ["gözlem sürüyor"]


def rapor(olc, ekler=None):
    """{cüzdan: dict(sinif, puan, gerekce, n, ort, medyan, pozitif)} — puana göre sıralı."""
    ekler = ekler or {}
    out = {}
    for w, m in olc.items():
        ek = ekler.get(w)
        s, g = sinif(m, ek)
        out[w] = dict(sinif=s, puan=puan(m, ek), gerekce=g, n=m["n"], ort=m["ort"], medyan=m["medyan"], pozitif=m["pozitif"])
    return dict(sorted(out.items(), key=lambda x: -x[1]["puan"]))


def sayim(r):
    s = {"A": 0, "B": 0, "C": 0}
    for v in r.values(): s[v["sinif"]] += 1
    return s


if __name__ == "__main__":                           # elle: python3 -m nexora.kopyalanabilirlik
    from nexora import kadro
    olc = kadro.olcum(os.getenv("ETIKET_DB", "nexora_etiket.db"))
    r = rapor(olc)
    s = sayim(r)
    print(f"Kopyalanabilirlik: A={s['A']}  B={s['B']}  C={s['C']}  (toplam {len(r)}; ek veri yok, yalnızca net getiri)")
    for w, v in r.items():
        print(f"  {w[:4]}…{w[-4:]}  {v['sinif']}  puan {v['puan']:>5}  n={v['n']:<3} ort %{v['ort']:+.2f}  "
              f"medyan %{v['medyan']:+.2f}  — {'; '.join(v['gerekce'])}")
