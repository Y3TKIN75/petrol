"""Olay kategorileri: filtre ve analiz ayni listeyi kullanir.

Referans katlar Subat-Agustos 2026 savas donemindeki 70 buyuk hareket gununden gelir
(arastirma/model_tasarim_bulgulari.md): kategori o gunun baskin nedeni oldugunda fiyat hareketinin,
onceki 20 islem gununun medyan |gunluk| hareketine orani. Eylul verisi bu referansa katilmadi (test).
"""

# kod: (modele verilen tanim, tarihsel referans)
KATEGORILER: dict[str, tuple[str, str]] = {
    "sevkiyat": ("chokepoint/route closure or closure threat, blockade, attack on or seizure of tankers",
                 "~3.5x normal when dominant (Hormuz 'will stay shut', full blockade ordered)"),
    "savas": ("new wave of military strikes, war start, ceasefire collapse, combat resumes",
              "~3.5x normal when it changes the state of the war (war start 6.8x, truce broken 3.5x, "
              "'ceasefire is over' 2.3x); another round of the same kind of strikes in an ongoing war ~1x "
              "(Mar 17: 0.9x)"),
    "diplomasi_ileri": ("talks agreed/scheduled, progress reported, ceasefire, deal, strikes paused, a major power or "
                        "mediator pressing a party to de-escalate, a party offering to reopen supply",
                        "~2x normal; ceasefire or signed deal up to ~5x; Pakistan/China pressing for new talks "
                        "(Jul 24) 1.8x; Iran saying Hormuz would reopen within a month (May 27) 1.8x"),
    "toparlanma": ("supply returns: chokepoint reopens, transits resume, terminal/pipeline restarts, rerouting",
                   "~2x normal; as large as the disruption it reverses"),
    "lider_tehdit": ("leader's specific threat or ultimatum (bombing, blockade, deadline)",
                     "~1.5x normal; vague or repeated threats fade within the day"),
    "diplomasi_cikmaz": ("talks fail, proposal rejected, claims denied by the other side, truce fragile, hard conditions, "
                         "a principal refusing to negotiate or to yield",
                         "~1.3x normal (1.0-2.4x); Trump rejecting Iran's proposal (Apr 29) 2.4x; a denial or "
                         "rejection after optimism-driven declines reverses that move (Mar 24-27)"),
    "altyapi": ("attack on or outage of energy infrastructure (field, refinery, pipeline, port), force majeure, output cut",
                "~1x normal for a single field/refinery (South Pars ~0x, Iraq force majeure 0.9x); larger when "
                "export capacity is lost, above all a route that bypasses a disrupted chokepoint (Fujairah export "
                "terminal 1.7x), or a new country's facilities are hit for the first time (Kuwait 2.8x); often "
                "partly reversed next day"),
    "lider_iyimser": ("leader says the war is ending or a deal is close, without a concrete step",
                      "first credible instance can be very large (~10x once); repeats ~0"),
    "uretim_politikasi": ("OPEC+/producer output policy, quotas, membership", "small during acute supply crises"),
    "rezerv_yaptirim": ("strategic reserve releases, sanctions or waivers, export bans",
                        "small during acute crises (record releases did not stop rallies); context can flip sign"),
    "talep_makro": ("demand, inventories, central banks, macro data", "usually below 0.75x normal"),
    "diger": ("anything else (statements about war, peace or talks belong in diplomasi_* or lider_*)", "-"),
}

# Bu kategorilerdeki ilgili haberler (fiyat haberi degilse) derin analize mutlaka girer:
# Eylul testinde 20b filtresi lider/diplomasi haberlerini 'onemsiz' sayip eledi.
ANALIZ_ZORUNLU = {"sevkiyat", "savas", "diplomasi_ileri", "toparlanma", "lider_tehdit", "diplomasi_cikmaz",
                  "altyapi", "lider_iyimser"}


def kategori_listesi(referansli: bool) -> str:
    lines = []
    for kod, (tanim, ref) in KATEGORILER.items():
        lines.append(f"  {kod}: {tanim}" + (f" [history: {ref}]" if referansli else ""))
    return "\n".join(lines)
