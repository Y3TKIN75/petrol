"""Subat-Agustos 2026 buyuk hareket gunleri ve sessiz gunler icin elle yapilan etiketler.

Etiketler arsiv basliklarinin (veri/haberler_buyuk.json, haberler_sessiz.json) tek tek okunmasiyla,
haberlerin kendi atfettigi nedenlere ve Wikipedia kronolojisine gore yapildi (Claude, 2026-10-03).
Fiyatlar veri/gunluk_bz_cl.csv'den okunur. Cikti: veri/etiketli_gunler.json
"""
import csv
import json
from datetime import date
from pathlib import Path

VERI = Path(__file__).parent / "veri"

KATEGORI = {
    "SAVAS": "Askeri tirmanma: yeni saldiri dalgasi, savas baslangici, ateskesin cokmesi",
    "ALTYAPI": "Enerji altyapisina saldiri/kesinti: tesis, rafineri, uretim kesintisi, mucbir sebep",
    "SEVKIYAT": "Bogaz/rota kapanmasi, abluka, tanker saldirisi veya el koyma",
    "TOPARLANMA": "Arzin geri donmesi: bogaz acilmasi, gecislerin baslamasi, terminalin yeniden acilmasi",
    "DIPLOMASI_ILERI": "Gorusme karari, ilerleme, ateskes, anlasma, saldirilarin durdurulmasi",
    "DIPLOMASI_CIKMAZ": "Gorusmelerin cokmesi, teklifin reddi, yalanlama, kirilganlik, katı sartlar",
    "LIDER_TEHDIT": "Liderin somut tehdidi/ultimatomu (bombalama, abluka, teslimiyet talebi)",
    "LIDER_IYIMSER": "Liderin 'savas bitiyor / anlasma yakin' beyani",
}

# gun: (birincil kategori, [ikincil], haberin yonu (+1/-1), lider/bakan beyani mi, yenilik, surucu)
BUYUK = {
    "2026-02-02": ("DIPLOMASI_ILERI", ["LIDER_IYIMSER"], -1, True, "ilk", "Trump Iran'in 'ciddi sekilde gorustugunu' soyledi; gorusmeler planlandi"),
    "2026-02-04": ("LIDER_TEHDIT", ["SAVAS"], +1, True, "ilk", "Trump: Iran lideri 'cok endiselenmeli'; ABD Iran IHA'sini dusurdu (gorusme kararina ragmen)"),
    "2026-02-18": ("DIPLOMASI_CIKMAZ", ["LIDER_TEHDIT"], +1, True, "gelisme", "Vance: Iran temel talepleri gormezden geldi, askeri secenek masada"),
    "2026-03-02": ("SAVAS", ["ALTYAPI"], +1, False, "ilk", "ABD-Israil'in Iran'a saldirisi, bolgesel savas; Suudi en buyuk rafineri durdu; Katar LNG durdu"),
    "2026-03-03": ("SEVKIYAT", ["ALTYAPI"], +1, False, "ilk", "Iran Hurmuz'u kapatti; Korfez'de tesisler kapandi"),
    "2026-03-05": ("SAVAS", ["SEVKIYAT"], +1, False, "gelisme", "Savas genisliyor; Iran kara harekatina karsi tehdit; Korfez depolari doluyor"),
    "2026-03-06": ("LIDER_TEHDIT", ["SAVAS"], +1, True, "ilk", "Trump: 'kosulsuz teslimiyet disinda anlasma yok' (Rus petrolu yaptirim gevsemesi etkisiz)"),
    "2026-03-09": ("SEVKIYAT", ["ALTYAPI"], +1, False, "gelisme", "Hurmuz trafigi coktu, Suudi uretim kesti; gun icinde Trump'in 'bitecek' imasiyla geri dondu"),
    "2026-03-10": ("LIDER_IYIMSER", ["DIPLOMASI_ILERI"], -1, True, "ilk", "Trump: savas 'buyuk olcude tamamlandi', 'cok yakinda' biter; IEA rekor stok salimi plani"),
    "2026-03-11": ("SAVAS", [], +1, False, "gelisme", "Iran Korfez'de ekonomik hedefleri vurdu; IEA salim plani ve Trump'in 'yakinda biter' tekrari etkisiz"),
    "2026-03-12": ("SEVKIYAT", [], +1, True, "ilk", "Iran: Hurmuz kapali kalacak; Irak tankerlerine saldiri; SPR salimi etkisiz"),
    "2026-03-13": ("ALTYAPI", ["SAVAS"], +1, False, "gelisme", "Suudi uretimi %20 kesildi; ABD Iran adasini bombaladi; Rus yaptirim muafiyeti etkisiz"),
    "2026-03-16": ("TOPARLANMA", [], -1, False, "ilk", "Bazi gemiler Hurmuz'den gecti"),
    "2026-03-17": ("SAVAS", ["LIDER_TEHDIT"], +1, False, "gelisme", "Iran BAE'ye yeniden saldirdi, Korfez tesislerini tehdit etti, Hurmuz'u kalici kapatma yemini"),
    "2026-03-18": ("ALTYAPI", [], +1, False, "ilk", "Israil Guney Pars'i vurdu; Iran Korfez enerji tesislerine saldirdi (Brent-WTI gercek ayrisma)"),
    "2026-03-20": ("ALTYAPI", ["SAVAS"], +1, False, "gelisme", "Irak mucbir sebep; enerji tesisleri hedefte; ek ABD askeri (yaptirim muafiyeti etkisiz)"),
    "2026-03-23": ("DIPLOMASI_ILERI", ["LIDER_IYIMSER"], -1, True, "ilk", "Trump enerji altyapisina saldiriyi 5 gun erteledi, gorusme iddia etti (Iran yalanladi)"),
    "2026-03-24": ("DIPLOMASI_CIKMAZ", [], +1, True, "gelisme", "Iran gorusme iddiasini yalanladi; onceki gunun dususunun bir kismi geri alindi"),
    "2026-03-26": ("DIPLOMASI_CIKMAZ", ["LIDER_TEHDIT"], +1, True, "gelisme", "Iran gorusmeleri yalanladi, Hurmuz gecis ucreti; Beyaz Saray 'cehennem' tehdidi"),
    "2026-03-27": ("DIPLOMASI_CIKMAZ", [], +1, True, "gelisme", "Iran ateskesi reddetti; Rubio yeni endise"),
    "2026-03-30": ("LIDER_TEHDIT", ["SAVAS"], +1, True, "gelisme", "Trump Iran enerji varliklarini havaya ucurmakla tehdit etti; Iran Israil rafinerisini vurdu"),
    "2026-03-31": ("LIDER_IYIMSER", [], -1, True, "gelisme", "Trump savasin 2-3 haftada bitebilecegini soyledi (Brent vade kalintisi)"),
    "2026-04-01": ("LIDER_IYIMSER", [], -1, True, "tekrar", "Trump 'savas 2-3 haftada biter' (Brent -%14.5 vade kalintisi, WTI -%1.2)"),
    "2026-04-02": ("LIDER_TEHDIT", ["SAVAS"], +1, True, "ilk", "Trump ulusa seslenis: Iran'i 2-3 hafta 'cok sert' vuracagiz; sivil altyapi bombalandi"),
    "2026-04-08": ("DIPLOMASI_ILERI", [], -1, True, "ilk", "Trump iki haftalik ateskes ilan etti"),
    "2026-04-09": ("DIPLOMASI_CIKMAZ", ["ALTYAPI"], +1, False, "gelisme", "Ateskes kirilgan; Hurmuz acik degil (ADNOC); Suudi boru hatti vuruldu"),
    "2026-04-13": ("DIPLOMASI_CIKMAZ", ["SEVKIYAT"], +1, True, "ilk", "Islamabad gorusmeleri basarisiz; ABD Iran limanlarina abluka"),
    "2026-04-14": ("DIPLOMASI_ILERI", ["LIDER_IYIMSER"], -1, True, "gelisme", "Yeni gorusme umutlari; Trump 'savas bitmeye cok yakin'"),
    "2026-04-16": ("DIPLOMASI_CIKMAZ", [], +1, False, "gelisme", "Gorusmelerin Hurmuz'u acacagina suphe; Kongre geri cekilmeyi reddetti"),
    "2026-04-17": ("TOPARLANMA", ["DIPLOMASI_ILERI"], -1, True, "ilk", "Iran Disisleri: Hurmuz acik; Trump 'anlasma 1-2 gun icinde'"),
    "2026-04-20": ("DIPLOMASI_CIKMAZ", ["SEVKIYAT", "LIDER_TEHDIT"], +1, True, "gelisme", "ABD Iran gemisine el koydu; Tahran 2. tur gorusmeyi reddetti; Trump 'bombalar patlar'"),
    "2026-04-21": ("DIPLOMASI_CIKMAZ", [], +1, False, "gelisme", "Ateskes uzatildi ama gorusmeler askida"),
    "2026-04-22": ("SEVKIYAT", [], +1, False, "ilk", "Iran Hurmuz'de 2 gemiye el koydu; konteyner gemilerine ates"),
    "2026-04-23": ("DIPLOMASI_CIKMAZ", ["SEVKIYAT"], +1, False, "gelisme", "Ateskeste catlaklar; Iran bas muzakerecisi istifa etti; mayin botlarini vurma emri"),
    "2026-04-28": ("DIPLOMASI_CIKMAZ", [], +1, True, "gelisme", "Trump'in Iran baris planini reddedecegi haberleri (BAE'nin OPEC'ten cikisi etkisiz)"),
    "2026-04-29": ("DIPLOMASI_CIKMAZ", ["LIDER_TEHDIT"], +1, True, "gelisme", "Trump Iran teklifini reddetti; abluka uzatma, askeri secenekler"),
    "2026-04-30": ("DIPLOMASI_ILERI", [], -1, False, "ilk", "Iran guncellenmis baris teklifini arabulucuya gonderdi"),
    "2026-05-01": ("DIPLOMASI_ILERI", [], -1, False, "gelisme", "Iran yeni teklif sundu (Trump 'memnun degilim')"),
    "2026-05-04": ("ALTYAPI", ["SEVKIYAT"], +1, False, "ilk", "Iran BAE'nin Fujairah limanini vurdu, Hurmuz'de gemilere saldirdi"),
    "2026-05-05": ("DIPLOMASI_ILERI", ["TOPARLANMA"], -1, True, "gelisme", "ABD-Iran anlasmaya yakin; Trump Project Freedom'i durdurdu; 2 gemi gecti"),
    "2026-05-06": ("DIPLOMASI_ILERI", [], -1, False, "gelisme", "ABD ve Iran'in anlasmaya yaklastigi raporlari"),
    "2026-05-12": ("DIPLOMASI_CIKMAZ", [], +1, True, "gelisme", "Trump: ateskes 'yasam desteginde'; baris umutlari sondu"),
    "2026-05-15": ("LIDER_TEHDIT", ["DIPLOMASI_CIKMAZ"], +1, True, "gelisme", "Trump 'Iran'a sabrim tukeniyor'; Iran 'Amerikalilara guvenemeyiz'"),
    "2026-05-18": ("LIDER_TEHDIT", ["ALTYAPI"], +1, True, "gelisme", "Trump 'saat isliyor'; BAE nukleer santrali vuruldu (sonra planli saldiri iptal)"),
    "2026-05-20": ("DIPLOMASI_ILERI", ["LIDER_IYIMSER"], -1, True, "gelisme", "Trump: gorusmeler 'son asamada'; baris taslagi raporlari"),
    "2026-05-26": ("DIPLOMASI_ILERI", [], -1, True, "gelisme", "Trump: gorusmeler iyi ilerliyor (yeni ABD saldirilarina ragmen)"),
    "2026-05-27": ("DIPLOMASI_ILERI", [], -1, True, "gelisme", "Rubio: gorusmelere 'her sans'; Iran devlet medyasi: Hurmuz bir ayda acilir (saldirilara ragmen)"),
    "2026-06-01": ("DIPLOMASI_CIKMAZ", ["SAVAS"], +1, False, "gelisme", "Iran gorusmeleri dondurdu; Israil Lubnan'da saldirilari artirdi"),
    "2026-06-04": ("DIPLOMASI_ILERI", ["LIDER_IYIMSER"], -1, False, "gelisme", "Israil-Lubnan ateskesi; Trump'in savasi yeniden baslatmak istemedigi raporu"),
    "2026-06-09": ("DIPLOMASI_ILERI", ["TOPARLANMA"], -1, True, "gelisme", "Iran ve Israil saldirilari durdurdu; Enerji Bakani: Hurmuz trafigi artiyor"),
    "2026-06-12": ("DIPLOMASI_ILERI", ["LIDER_IYIMSER"], -1, True, "gelisme", "Trump anlasmanin yakin oldugunu soyledi"),
    "2026-06-15": ("DIPLOMASI_ILERI", [], -1, True, "ilk", "Trump: anlasma imzalandi; gecici ABD-Iran anlasmasi"),
    "2026-06-16": ("TOPARLANMA", [], -1, False, "gelisme", "Anlasma sonrasi Hurmuz akisinin toparlanacagi beklentisi (2. gun devam)"),
    "2026-06-24": ("TOPARLANMA", [], -1, True, "gelisme", "Tankerler Hurmuz'den geciyor; Trump 'gecis ucreti olmayacak'"),
    "2026-06-26": ("TOPARLANMA", [], -1, False, "ilk", "Suudi Ras Tanura 4 ay sonra yuklemeye basladi"),
    "2026-07-07": ("SEVKIYAT", ["LIDER_TEHDIT", "DIPLOMASI_CIKMAZ"], +1, True, "ilk", "Hurmuz'de Suudi/Katar tankerleri vuruldu; Trump anlasmanin 'bittigini' soyledi"),
    "2026-07-08": ("SAVAS", ["DIPLOMASI_CIKMAZ"], +1, True, "gelisme", "Trump: ateskes 'bitti'; ABD Iran'i vurdu, Iran 3 Korfez ulkesine ates acti"),
    "2026-07-13": ("SEVKIYAT", ["SAVAS"], +1, True, "ilk", "ABD tum Iran kiyisina abluka karari; karsilikli saldirilar"),
    "2026-07-17": ("ALTYAPI", ["SEVKIYAT"], +1, False, "ilk", "Iran Kuveyt'te enerji/tuzdan arindirma tesisini vurdu; Kizildeniz kapatma tehdidi"),
    "2026-07-22": ("SEVKIYAT", ["DIPLOMASI_CIKMAZ"], +1, True, "ilk", "Husiler Kizildeniz'de Suudi tankerlerini hedef aldi; Rubio 'Iran ciddi degil'"),
    "2026-07-23": ("SEVKIYAT", ["SAVAS"], +1, False, "gelisme", "Husiler Suudi tankerlerini vurdu (Kizildeniz ablukasi); Trump cezalandirma yemini"),
    "2026-07-24": ("DIPLOMASI_ILERI", ["TOPARLANMA"], -1, False, "ilk", "Pakistan/Cin'in yeni gorusme icin bastirdigi raporu"),
    "2026-07-27": ("DIPLOMASI_ILERI", [], -1, True, "ilk", "ABD ve Iran saldirilari diplomasi icin durdurdu (Cizan yanginina ragmen)"),
    "2026-07-28": ("DIPLOMASI_ILERI", [], -1, False, "gelisme", "Saldirisiz gunler suruyor (Cizan rafinerisi kapandi, etkisiz)"),
    "2026-07-29": ("SAVAS", ["SEVKIYAT"], +1, True, "ilk", "Ara bozuldu: Iran ABD guclerine saldirdi, ABD-Suudi Irak'ta saldiri, Husi tanker saldirisi"),
    "2026-08-03": ("DIPLOMASI_ILERI", ["LIDER_IYIMSER"], -1, True, "gelisme", "Trump saldirilari durdurdu, gorusmelerin basladigini soyledi (Iran yalanladi)"),
    "2026-08-04": ("DIPLOMASI_ILERI", [], -1, True, "gelisme", "Bessent: Hurmuz anlasmasi gunler icinde; Axios: duyuru hedefleniyor"),
    "2026-08-06": ("DIPLOMASI_CIKMAZ", [], +1, False, "ilk", "Iran Hurmuz icin kisitlayici taslak plan / ABD-Israil gemilerine yasak tasarisi"),
    "2026-08-10": ("DIPLOMASI_CIKMAZ", ["LIDER_TEHDIT"], +1, True, "gelisme", "Hurmuz anlasmasi umudu sondu; Iran acilisi ABD tavizine bagladi"),
    "2026-08-25": ("DIPLOMASI_ILERI", [], -1, True, "ilk", "ABD saldiri yerine yaptirima gecti (gerilim azalmasi olarak okundu); Iran-Umman Hurmuz uzlasisi"),
}

# Sessiz gun nedenleri
NEDEN = {
    "DENGELEYICI": "Ayni gun zit yonlu haberler (or. saldiri + anlasma raporu)",
    "FIYATLANMIS": "Buyuk hareketten sonraki gun; haber zaten fiyatta",
    "TEKRAR": "Tekrarlanan tehdit/saldiri/iddia; piyasa alismis",
    "GUN_ICI_SONUM": "Gun icinde sert tepki, kapanisa kadar sondu",
    "KARSI_VERI": "Resmi akis/stok verisi saldiri haberini dengeledi",
    "GECIKMELI": "Tepki ertesi gun geldi",
    "BEKLEME": "Kritik olay oncesi bekleme (gorusme tarihi vb.)",
}
SESSIZ = {
    "2026-02-06": (["DENGELEYICI"], "Gorusmelerin devami + gerilim"),
    "2026-02-23": (["BEKLEME"], "Gorusmeler oncesi bekleme"),
    "2026-02-25": (["DENGELEYICI"], "Suudi uretim/ihracat artisi + gerilim; ABD stok artisi"),
    "2026-02-26": (["BEKLEME", "DENGELEYICI"], "Gorusmeler 'onemli ilerleme' ile bitti ama tepki kucuk"),
    "2026-03-04": (["FIYATLANMIS", "DENGELEYICI"], "Hurmuz kapali ama 2 gunde +%12 olmus; Bessent tanker destegi"),
    "2026-04-06": (["GUN_ICI_SONUM", "TEKRAR"], "Trump'in kufurlu tehdidiyle acilista 113-115$; kapanista sondu"),
    "2026-05-19": (["DENGELEYICI"], "Trump saldiriyi erteledi + 'bir buyuk darbe daha' + Vance ilerleme"),
    "2026-05-22": (["DENGELEYICI"], "Gorusmelere suphe; kucuk yukselis"),
    "2026-05-28": (["DENGELEYICI", "GUN_ICI_SONUM"], "ABD saldirisi ve Iran'in ussu vurmasi + ateskes uzatma raporu"),
    "2026-06-17": (["FIYATLANMIS", "DENGELEYICI"], "Anlasma metni; 2 gunde -%10 sonrasi; Hurmuz'den 12m varil + yeniden saldiri riski"),
    "2026-07-02": (["FIYATLANMIS"], "Suudi ihracati savas oncesine yakin; fiyat zaten savas oncesi seviyede"),
    "2026-07-06": (["DENGELEYICI", "GUN_ICI_SONUM"], "Suudi rekor fiyat indirimi + gemi saldirilari (+%5 gun ici)"),
    "2026-07-15": (["FIYATLANMIS"], "Iran'in ihracati engelleme tehdidi; buyuk ralli sonrasi"),
    "2026-07-16": (["GECIKMELI"], "Kuveyt tesis saldirisi; tepki ertesi gun (+%4.5)"),
    "2026-08-05": (["DENGELEYICI", "TEKRAR"], "Husi tanker saldirisi iddiasi (rutin) + Iran-Umman gorusme umudu"),
    "2026-08-12": (["KARSI_VERI", "TEKRAR"], "Kizildeniz/Umman gemi saldirilari + ABD: Hurmuz'den 9 mb/g, stoklar artti"),
    "2026-08-18": (["DENGELEYICI"], "Hurmuz'de kargo gemisi saldirisi + Suudi Hurmuz sevkiyatina dondu"),
    "2026-08-21": (["DENGELEYICI"], "Trump Iran ortaklarina yaptirim tehdidi + Iran cumhurbaskani 'savas bitsin'"),
    "2026-08-26": (["DENGELEYICI"], "Beyaz Saray 'gorusme yok' + Iran-Umman Hurmuz adimi"),
    "2026-08-28": (["FIYATLANMIS"], "Hurmuz mayinlari temizlendi, Trump 'Hurmuz acik' (kucuk tepki)"),
}


def main() -> None:
    prices = {r["day"]: r for r in csv.DictReader((VERI / "gunluk_bz_cl.csv").open(encoding="utf-8"))}
    out = {"kategori_tanimlari": KATEGORI, "sessiz_neden_tanimlari": NEDEN, "buyuk": [], "sessiz": []}
    for day, (kat, ikincil, yon, lider, yenilik, surucu) in BUYUK.items():
        p = prices[day]
        b, w = float(p["brent_pct"]), float(p["wti_pct"])
        # Brent/WTI ayrismasi olan gunlerde (vade kalintisi olabilir) WTI esas
        ref = w if p["flag"] else (b + w) / 2
        out["buyuk"].append({
            "gun": day, "haftanin_gunu": date.fromisoformat(day).strftime("%a"), "brent_pct": b, "wti_pct": w,
            "tutarsiz": bool(p["flag"]), "hareket_pct": round(ref, 2), "kategori": kat, "ikincil": ikincil,
            "haber_yonu": yon, "yon_tutarli": (ref > 0) == (yon > 0), "lider_beyani": lider, "yenilik": yenilik,
            "hafta_sonu_haberi": date.fromisoformat(day).weekday() == 0, "surucu": surucu,
        })
    for day, (nedenler, aciklama) in SESSIZ.items():
        p = prices[day]
        out["sessiz"].append({"gun": day, "brent_pct": float(p["brent_pct"]), "wti_pct": float(p["wti_pct"]),
                              "nedenler": nedenler, "aciklama": aciklama})
    (VERI / "etiketli_gunler.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out['buyuk'])} buyuk, {len(out['sessiz'])} sessiz gun etiketlendi")


if __name__ == "__main__":
    main()
