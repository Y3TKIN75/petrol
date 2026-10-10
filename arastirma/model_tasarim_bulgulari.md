# Model tasarımı için bulgular: Şubat–Ağustos 2026 savaş dönemi

**Hazırlanma:** 3 Ekim 2026 (Claude, oturum analizi)
**Kapsam:** 2 Şubat – 31 Ağustos 2026 arasındaki 146 işlem günü. Brent veya WTI'nin %3 ve üzeri oynadığı 70 gün tek tek etiketlendi. Karşılaştırma için %1'in altında kalan 20 "sessiz" gün incelendi. Eylül, yeni modelin testi için ayrıldı.
**Veri:** `arastirma/veri/etiketli_gunler.json` (etiketler), `haberler_buyuk.json` / `haberler_sessiz.json` (~31.000 arşiv başlığı), `gunluk_bz_cl.csv`, `saatlik_cl.csv`. Etiketlerin kaynağı: `arastirma/etiketle.py`. İstatistikler: `arastirma/istatistik.py`, `arastirma/hareket_yapisi.py`.

---

## 1. Kısa sonuç

1. **Bu dönemde petrolü en çok diplomasi oynattı.** 70 büyük günün 37'sinin baskın nedeni diplomasi: 21 gün ilerleme, 16 gün çıkmaz. Fiziki arz olayları (savaş, sevkiyat, altyapı, toparlanma) yalnızca 24 günde baskın neden. 42 günde bir lider ya da bakan beyanı belirleyici rol oynadı.
2. **Piyasa doğrulanmış gerçeğe değil, güvenilir rapora tepki veriyor.** "ABD ve İran anlaşmaya yakın" (CNN, adı verilmeyen kaynak) −%7,8. "Trump, İran'ın barış planını reddedecek" (Reuters, haber) +%3. Mevcut modelimiz bu tür haberleri "iddia" diye 0,7 katsayıyla cezalandırıyor. Oysa piyasayı asıl hareket ettiren haberler bunlar.
3. **Etki büyüklükleri modelin "orta" varsayımının çok üstünde.** Baskın neden olduğunda tipik hareket %3-6, en uç örnekler %10-16 (ateşkes ilanı, Hürmüz'ün açık ilan edilmesi, savaşın başlaması). Model ise neredeyse her habere "orta (%1-3)" diyor.
4. **Somut adım ile söylem ayrılmalı.** İlk "savaş bitiyor" sözü −%11 getirdi. Ertesi gün aynı söz tekrarlanınca etkisi sıfırdı. Liderin iyimser sözleri ancak somut bir adımla birlikte geldiğinde etkili oluyor: görüşme tarihi, saldırıların durdurulması, taslak metin. Tehditler de somut olduğunda (abluka, altyapıyı bombalama, son tarih) etkili; genel tehditler gün içinde sönüyor.
5. **Karşı tarafın yanıtı kritik.** ABD'nin iddiasını İran yalanlayınca düşüş 1-4 gün içinde geri alındı (23 → 24-27 Mart, 17 → 20 Nisan). ABD somut bir adım attığında ise yalanlama daha az önemliydi (3 Ağustos).
6. **Sessiz günlerin çoğunda dengeleyici haberler var.** 20 sessiz günün 13'ünde aynı gün zıt yönlü haberler bulunuyor: saldırı ile anlaşma raporu ya da tehdit ile ertelenmiş saldırı. Tek tek olay uyarıları yetmez; **günün net resmi** de gerekli.
7. **Arzın geri dönmesi, bozulması kadar fiyat oynatıyor.** Toparlanma günlerinin medyan hareketi %4,1. Örnekler: Hürmüz'ün açılması −%9/−%11, Ras Tanura'nın yeniden açılması −%4, ve kullanıcının Aramco örneği.
8. **Kriz anında yapısal ve politik arz önlemleri etkisiz.** BAE'nin OPEC'ten çıkışı, IEA'nın rekor rezerv salımı, ABD SPR salımları ve Rus petrolüne yaptırım muafiyetleri savaş anlatısına karşı fiyatı düşüremedi.
9. **Aynı haber türü bağlama göre ters etki yapabiliyor.** 25 Ağustos'ta "tarihin en sert yaptırımları" fiyatı %3,9 düşürdü, çünkü piyasa bunu "saldırı yerine yaptırım", yani gerilimin azalması olarak okudu.

## 2. Veri ve yöntem

- **Büyük gün:** max(|Brent %|, |WTI %|) ≥ 3. 70 gün; Pazartesiler 16 gün (%23).
- **Etiket:** Her gün için arşiv başlıklarının (Google News, 4 sorgu, gün başına ~150-360 başlık) fiyat hareketini nedeniyle birlikte veren kısımları okundu, baskın neden ve ikincil nedenler etiketlendi. Wikipedia'daki "2026–2028 world oil market chronology" ile çapraz kontrol edildi.
- **Brent/WTI ayrışması:** 10 günde iki seri ters yönde ya da 3 puandan fazla farklı. Bir kısmı vade geçişi kalıntısı: 1 Nisan Brent −%14,5, WTI −%1,2. Bir kısmı gerçek: 18 Mart'ta Orta Doğu tesislerine saldırı Brent'i +%3,8 yükseltirken WTI yatay kaldı. Bu günlerde WTI esas alındı.
- **Saatlik yapı:** WTI saatlik veri, seans gününe (22:00 UTC açılış) göre hizalandı.

## 3. Bulgular (kanıtlarıyla)

### 3.1 Kategori bazında etki

Ölçüt, ilgili kategori o günün baskın nedeni olduğundaki hareket. Kategori başına vaka az; bu değerler kesin değil, yön gösterici.

| Kategori | Gün | Medyan \|%\| | Aralık | Ertesi gün (medyan) | Örnek |
|---|---|---|---|---|---|
| Savaş/tırmanma | 6 | 5,8 | 3,0–8,5 | devam (+%36) | 2 Mart savaşın başlaması (+%7), 8 Temmuz "ateşkes bitti" (+%5) |
| Sevkiyat/abluka | 8 | 5,1 | 2,2–9,5 | devam (+%24) | 12 Mart "Hürmüz kapalı kalacak" (+%9,5), 13 Temmuz kıyı ablukası (+%9,5) |
| Diplomasi ilerleme | 21 | 4,8 | 2,5–16,4 | hafif devam (+%14) | 8 Nisan ateşkes (−%16), 15 Haziran anlaşma imzası (−%5) |
| Diplomasi çıkmazı | 16 | 4,3 | 2,5–6,5 | devam (+%29) | 29 Nisan teklif reddi (+%6/+%7), 24 Mart İran yalanlaması (+%5) |
| Toparlanma | 5 | 4,1 | 4,0–10,3 | geri dönüş (−%52) | 17 Nisan Hürmüz açık (−%11), 26 Haziran Ras Tanura (−%4) |
| Lider tehdidi | 6 | 3,5 | 2,8–12,2 | hafif geri dönüş | 2 Nisan "çok sert vuracağız" (+%11), 6 Mart "koşulsuz teslimiyet" (+%12) |
| Altyapı saldırısı | 5 | 2,9 | 0,1–5,1 | geri dönüş (−%78) | 4 Mayıs Fujairah (+%5, ertesi gün −%4) |
| Lider iyimserliği (tek başına) | 3 | 1,5 | 1,2–11,6 | – | 10 Mart ilk "savaş bitiyor" (−%11); tekrarlar etkisiz |

**Çıkarım:** Savaş, sevkiyat ve diplomasi değişimleri günlerce sürebiliyor. Tekil altyapı saldırıları, tehditler ve toparlanma haberleri ise genelde ertesi gün kısmen geri alınıyor.

### 3.2 Hareketin yapısı

- **Şok tipi:** 49 tutarlı büyük günün 29'unda (%59) hareketin yarısından fazlası tek bir saatte gerçekleşti. Fiyat ağırlıkla tekil haberlerle sıçrıyor.
- **Açılış etkisi:** 11 günde (%22) en büyük saat seans açılışında (22:00-23:00 UTC = 01:00-02:00 TSİ). Piyasa kapalıyken gelen haberler açılışta topluca fiyatlanıyor.
- **Ertesi gün yazı-tura:** Büyük hareketten sonraki gün aynı yönde devam oranı 24/49. Değer, ilk saatlerde haberi yakalamakta.

### 3.3 Lider beyanları: söz değil, içerik

| Tür | Etkili örnek | Etkisiz örnek |
|---|---|---|
| Somut karar/eylem | 8 Nisan ateşkes ilanı (−%16); 23 Mart saldırının ertelenmesi (−%11); 27 Temmuz saldırıların durdurulması (−%8) | – |
| Somut tehdit | 2 Nisan "2-3 hafta çok sert vuracağız" + sivil altyapı (+%11); 13 Temmuz abluka (+%9,5) | 6 Nisan küfürlü tehdit: açılışta +5$, kapanışta yatay |
| İyimserlik söylemi | 10 Mart ilk kez "savaş tamamlandı" (−%11) | 11 Mart aynı sözün tekrarı (etkisiz, fiyat +%5); Ekim'deki "çok yakında biter" |
| İyimserlik + somut adım | 20 Mayıs "son aşamada" + taslak metin (Brent −%5,6 / WTI −%8,8); 14 Nisan "bitmeye yakın" + yeni görüşme tarihi (Brent −%4,6 / WTI −%7,9) | – |

Kaynak: `arastirma/veri/etiketli_gunler.json`. Basında da 27 ve 31 Mart'ta "Trump'ın sözlü müdahalesi etkisini yitiriyor" yorumları var.

### 3.4 Barış iyimserliği ve hayal kırıklığı döngüsü

- **Geri alınan düşüşler:** 23 Mart (−%11) 24-27 Mart'ta tamamen geri alındı, çünkü İran yalanladı ve ateşkesi reddetti. 8 Nisan (−%16) ertesi gün kırılganlık haberleriyle kısmen geri alındı. 17 Nisan (−%11) 20 Nisan'da gemiye el konulması ve görüşmenin reddedilmesiyle +%7 geri geldi.
- **Kalıcı düşüşler:** 15-16 Haziran (anlaşma imzası, iki gün üst üste −%5) ve 27-28 Temmuz (saldırıların durdurulması, −%8 ve −%5) kalıcı oldu. Bu olaylar somut ve karşı tarafça kabul edilmişti.
- **Çıkarım:** Barış haberinde iki soru belirleyici: "Somut bir adım mı?" ve "Karşı taraf ne diyor?"

### 3.5 Sessiz günler: neden fiyat oynamadı?

| Neden | 20 günde |
|---|---|
| Dengeleyici haberler (aynı gün zıt yönlü) | 13 |
| Fiyatlanmış (büyük hareketin ertesi günü) | 5 |
| Gün içinde sert tepki, kapanışta sönmüş | 3 |
| Tekrar (rutinleşmiş saldırı ya da iddia) | 3 |
| Bekleme (kritik görüşme öncesi) | 2 |
| Karşı veri (resmi akış/stok verisi) | 1 |
| Gecikmeli tepki (ertesi gün) | 1 |

Not: Günlük kapanış verisi gün içi tepkiyi gizliyor. Örneğin 6 Nisan'da açılışta +5$, 6 Temmuz'da gün içinde +%5 vardı ama ikisi de günü yatay kapattı. Farkındalık amacı için bu gün içi tepkiler de önemli.

### 3.6 Bağlam etkisi: aynı haber, farklı sonuç

- **Mart (tırmanma rejimi):** Rezerv salımı, sigorta garantisi ve Rus yaptırım muafiyeti yükselişi durduramadı.
- **Mayıs sonu (diplomasi rejimi):** ABD İran'ı vururken bile "görüşmeler ilerliyor" haberleri fiyatı %3-5 düşürdü (26-27 Mayıs).
- **25 Ağustos:** Yeni yaptırımlar "saldırı yerine yaptırım" olarak okundu ve fiyat düştü.
- **Çıkarım:** Modele, son günlerdeki baskın anlatı ve fiyat eğilimi bağlam olarak verilmeli.

### 3.7 Brent ve WTI

Orta Doğu kaynaklı olaylar Brent'i daha çok etkiliyor (18 Mart, 22 Nisan'da Brent +%3,5 iken WTI +%0,9). Canlı sistemdeki "WTI teyidi olmadan Brent hareketi sayılmaz" kuralı bu günlerde gerçek bir hareketi gözden kaçırır. Yahoo'daki kontrat karışıklığı ise vade sonuna yakın dönemde yoğunlaşıyor (30 Mart-2 Nisan, Eylül'ün ikinci yarısı).

## 4. Mevcut modelin hataları ile eşleştirme

| Gözlenen hata (Eylül testi ve 3 Ekim canlı incelemesi) | İlgili bulgu |
|---|---|
| Hiç 🔴 yok; her şey "orta" | 3.1: Baskın olaylarda tipik hareket %3-6 |
| Lider beyanları filtrede kayboluyor ya da düşük puan alıyor | 1: Büyük günlerin %60'ında lider beyanı var |
| Reuters/Axios haberleri "iddia" olarak cezalanıyor | 2: Piyasa güvenilir rapora tepki veriyor |
| Tekrarlanan söylem (Trump "yakında biter") yanlış puanlanıyor | 3.3: Tekrarın etkisi yok |
| Onarım/yeniden başlama haberleri hafife alınıyor | 7: Toparlanma da %4+ oynatıyor |
| Aynı anda zıt haberler ayrı ayrı uyarı üretiyor | 3.5: Sessiz günlerin 13/20'si dengeleyici |
| Yayın tarihi ile olay tarihinin karışması, kopya haberler, propaganda | 3 Ekim canlı inceleme |

## 5. Model tasarım önerisi

Öncelik sırasıyla:

**A. Kategori sistemi:** `olay_turu` alanı bu dönemi açıklayan 8 kategoriyle değiştirilmeli: SAVAS, SEVKIYAT, ALTYAPI, TOPARLANMA, DIPLOMASI_ILERI, DIPLOMASI_CIKMAZ, LIDER_TEHDIT, LIDER_IYIMSER. Filtre (20b) ve analiz aynı kategorileri kullanmalı. Her kategorinin tarihsel etki aralığı istem içinde referans olarak verilmeli.

**B. Kesinlik yerine iki ayrı alan:**
- **kaynak_guvenilirligi:** ana akım ajans ve resmi kaynak / tek kaynaklı güvenilir rapor / taraf medyası (SABA, Tasnim, IRNA) / tabloid.
- **somutluk:** somut adım ya da karar (ateşkes ilanı, saldırının durdurulması, abluka emri, görüşme tarihi) / somut tehdit (son tarih, hedef) / söylem.

Skor, piyasanın asıl tepki verdiği şeyi ölçmeli: güvenilir kaynaktan gelen somut haber. "Doğrulanmamış" olması tek başına ceza sebebi olmamalı.

**C. Oynaklığa göre büyüklük:** Model yüzde tahmin etmek yerine etkiyi "normal bir günün kaçı kadar" diye vermeli. Kod, son 20 günün medyan mutlak günlük hareketini hesaplayıp bunu yüzdeye çevirmeli. Mart'ta normal bir gün ~%5, Eylül'de ~%2-3. Böylece rejim değişince model yeniden kalibre edilmiş olur.

**D. Bağlam alanları (modele sorulacak):**
- **karsi_taraf:** Teyit etti mi, yalanladı mı, yanıt yok mu? Yalanlama gelirse ilgili önceki olay yeniden skorlanmalı.
- **tekrar_sayisi:** Son 14 günde aynı içerikte kaç beyan/olay var? Kod bunu bir azaltma katsayısı olarak uygulamalı.
- **hakim_anlati:** Dünya durumuna otomatik eklenmeli (son 5-10 günün fiyat eğilimi ve baskın tema). Bu, çelişen haberlerde hangisinin ağır basacağını belirliyor.

**E. Net görünüm özeti:** Tek tek olay uyarılarına ek olarak her 4 saatte bir ve piyasa açılışından önce (pazar 21:30 UTC) son olayları birleştiren bir "net yön + güven + dengeleyici unsurlar" özeti. Bir olay aynı saatlerdeki zıt yönlü bir olayla dengeleniyorsa uyarıya bu not düşülmeli.

**F. Kapalı piyasa kuyruğu:** Hafta sonu ve gece gelen olaylar "açılış beklentisi" olarak toplanıp açılıştan önce tek bir özetle bildirilmeli. Büyük hareketlerin %22'si açılışta oluyor.

**G. Fiyat kontrolü:** WTI teyidi yalnızca Brent'in vade geçişi döneminde (vade sonundan önceki ~15 gün) şart olmalı. Diğer dönemlerde Brent'teki hareket tek başına kabul edilmeli.

**H. Kaynak listesi:** Taraf medyası (SABA, Tasnim, Press TV, IRNA) ve tabloid alan adları için sabit bir liste. Bu kaynaklardan gelen haberin kaynak güvenilirliği otomatik olarak düşük atanmalı. Kopya haberler tek kaynak sayılmalı (bu kısmı Claude analizlerinde yaptık; LLM şemasına `bagimsiz_kaynak` alanı eklenmeli).

**I. Olay tarihi:** Analiz şemasına `olay_tarihi` (haberde geçiyorsa) alanı eklenmeli. Olay 24 saatten eskiyse otomatik olarak "tekrar" sayılmalı.

**J. Kriz döneminde düşük öncelik:** Rezerv salımları, yaptırım muafiyetleri, OPEC üyeliği gibi yapısal haberler. Bunlar akışta gösterilmeli ama düşük puan almalı.

## 6. Sınırlar

- Etiketleri, sonuçları bilerek ben yaptım. Haber-fiyat eşleşmeleri gazetecilerin atıflarına dayanıyor. Aynı gün birden fazla neden olduğunda ayrıştırma bir yargıdır.
- Kategori başına vaka sayısı az (3-21) ve seçim yanlılığı var: yalnızca büyük günler ve rastgele 20 sessiz gün incelendi. "Bu haber geldiğinde ortalama ne olur" sorusu için bütün günlerin etiketlenmesi gerekir.
- Dönem tek bir rejimi kapsıyor: ABD/İsrail-İran savaşı, Hürmüz krizi. Barış döneminde katsayılar farklı olacaktır. C maddesindeki oynaklığa göre ölçekleme bunu kısmen giderir.
- Yahoo verisi vade dönemlerinde güvenilmez. Gün içi analiz WTI ile yapıldı.

## 7. Uygulama durumu (3 Ekim 2026)

Kullanıcı A + B + C'yi seçti. Uygulandı ve 10 Ekim'de Eylül vakalarıyla test edildi (7.1).

- **A. Kategoriler:** `petrol/kategoriler.py`. Filtre ve analiz aynı 12 kategoriyi kullanıyor: bu raporun 8 kategorisi + üretim politikası, rezerv/yaptırım, talep/makro, diğer. Analiz isteminde her kategorinin Şubat-Ağustos referansı "normalin katı" olarak yer alıyor. Filtrede savaş, sevkiyat, diplomasi, lider, altyapı ve toparlanma kategorilerindeki ilgili haberler (fiyat haberi değilse) kodla analize gönderiliyor.
- **B. Kaynak güvenilirliği + somutluk:** `kesinlik` alanının yerini aldı. Somutluğa, raporun gerektirdiği `gelisme_raporu` (güvenilir gelişme haberi) seviyesi eklendi. Analiz istemine Şubat-Ağustos dersleri kısa maddeler halinde eklendi.
- **C. Oynaklığa göre büyüklük:** `petrol/regime.py`, son 20 işlem gününün medyan |günlük| hareketini hesaplıyor (ayrışma günlerinde WTI esas). Model `beklenen_etki` alanını normalin katı olarak veriyor: normalin altı / normal / büyük / çok büyük. Kayıtta yaklaşık yüzde de saklanıyor.
- **Seviye eşikleri:** Yeni katsayılardan türetildi, veriye göre ayarlanmadı: 🔴 60, 🟡 35 (türetme `petrol/config.py` içinde).
- **Testler:** 40 birim testi geçiyor. Yeni kuralların 5 mutasyon testi yakalandı.
- **Eski analizler:** Eski şemayla kaydedilenler yeniden skorlanmıyor, saklanan skorları korunuyor.

### 7.1 Eylül testi (10 Ekim 2026)

19 Eylül vakası, gpt-oss-120b ile iki kez çalıştırıldı. Sonuçlar `arastirma/backtest/sonuc_v3_model_v2.json` ve `sonuc_v3_model_v2_tekrar.json` dosyalarında.

| Ölçüt | v1 (eski model) | v3 1. tur | v3 2. tur |
|---|---|---|---|
| Filtreden geçen | 15/19 | 19/19 | 19/19 |
| Yön doğru | 14/15 | 18/19 | 19/19 |
| Güçlü olay en az 🟡 | 8/13 | 10/13 | 9/13 |
| Güçlü olay 🔴 | 0/13 | 3/13 | 3/13 |
| Kontrol haberlerinde yanlış alarm | 0/10 | 0/10 | 0/10 |
| Ortalama skor: güçlü / orta / zayıf | 52 / 44 / 54 | 46 / 49 / 28 | 42 / 47 / 26 |

Yalnızca test bölümü (H vakaları, 7'si güçlü): güçlü olay en az 🟡 v1'de 3/7, v2'de 3/7, v3'te 5/7 ve 4/7.

**İyileşenler**
- Filtre artık hiçbir vakayı elemiyor ve kontrol haberlerinde yanlış alarm yok. Not: bu düzeltme Eylül filtre hataları görülerek yapıldı. Bu yüzden filtre sonucu tam bağımsız bir kanıt değil.
- İlk kez 🔴 çıktı: C2 tanker saldırısı, C5 Kızıldeniz limanı, H9 boru hattının yeniden açılması (iki turda da). C1 (orta) da 🔴.
- Zayıf olay H11 (SPR 40 milyon varil) 🟡'dan 📋'a indi. Not: H9 ve SPR senaryoları skor katsayıları belirlenirken birim testi beklentisi olarak kullanıldı. Model etiketleri bağımsız, ama bu iki sonuç kısmen tasarımdan geliyor.
- Somut eylem içeren olaylar tutarlı: tanker, liman, altyapı ve toparlanma vakalarında iki tur arasındaki skor farkı çoğunlukla 10 puanın altında.

**Kalan sorunlar (iki turda da aynı)**
1. **Somut adım olmayan beyanlar fazla eziliyor.** C7 (Trump "anlaşma aramıyorum"), H1 (Çin, İran'dan Husi saldırılarını sınırlamasını istiyor), H4 (İran cumhurbaşkanı "asla teslim olmayız") ve H3 (İran "7 günde Hürmüz'ü açabiliriz, şu şartla") 0-35 puan aldı. Model bunları "söylem / şartlı söz" ve "normalin altı" diye etiketledi. Güçlü olaylarda ortalamanın orta olayların altında kalmasının nedeni bu dört vaka. Bu dördü çıkarıldığında güçlü olay ortalaması 59, bu dördünün ortalaması 15.
   - En net hata H1: 15 dakikada Brent −%4,0. H3'te vadeli −%3,4.
   - C7 ve H4'ün etiketi zayıf: C7 aynı gün başka büyük haberlerle birlikte, H4'te hareketin zamanlaması bilinmiyor.
   - Muhtemel neden: istemdeki "tekrarlanan iyimser söylem ~0" dersi, ilk kez gelen sert tutum ve büyük güç baskısı haberlerine de uygulanıyor. Model dördünü de "yeni" diye işaretlediği halde etkiyi düşük tahmin etti.
   - Lider tabanı (en az 🟡) yalnızca etki "normalin altı" değilse devreye giriyor. Bu vakalarda model "normalin altı" dediği için taban çalışmadı.
2. **Altyapı saldırıları hep "normal" etkide kalıyor.** C3, C8, C9 ve H5 39-56 puanla 🟡 aldı, hiçbiri 🔴 değil. Kategori referansı "~1x, büyük ihracat kapasitesi kaybedilmedikçe" diyor. Model C8'deki istisnayı (Doğu-Batı boru hattının kapanması) uygulamadı. Uyarı yine veriliyor, yalnızca seviye düşük.
3. **H14 (G7'nin 100 milyon varil salımı) 📋'a indi.** Brent kapanışı ~%0, WTI gün içi −%4. Tartışmalı bir vaka, ancak orta etiketliydi.
4. **Sınırda vakalar oynak.** H3 35 → 15, H13 41 → 24. Eşiğe yakın vakalarda tek çalıştırmaya güvenilmemeli.

**Yöntem notu:** Eylül artık model v2 için kullanıldı. Yukarıdaki sorunlara yönelik bir düzeltme Eylül'e bakılarak yapılacağı için, onu doğrulamak için yeni bir test seti gerekir (Ekim vakaları).

### 7.2 Alan bazında denetim ve model v2.1 (10 Ekim 2026)

7.1 yalnızca son seviyeye bakıyordu. Bu bölümde 120b'nin her alanı, gerçekleşen hareketin o günkü normal harekete oranıyla karşılaştırıldı (19 vaka × 2 tur).

**120b'nin hataları**

| Hata | Vakalar | Not |
|---|---|---|
| Etki küçümseniyor: belirsizlik büyüklükten düşülüyor | H1, H3 (gerçek ~2x, tahmin <0,75x); C8, C3, H5 (gerçek 1,6-2,4x, tahmin "normal") | Gerekçelerde "uyulup uyulmayacağı belirsiz, o yüzden etki sınırlı", "onarım süresi belirsiz" geçiyor. Belirsizlik güvene gitmeli. |
| Yeni tutum "söylem" sayılıyor | C7, H4 | "Anlaşma aramıyorum", "teslim olmayız". Şubat-Ağustos'ta teklif reddi ve yalanlama 1-2,4x idi. |
| Fiyat eğilimini görmüyor | H4 | 22-23 Eylül: beş günlük diplomasi kaynaklı düşüş sonrası "teslim olmayız" (CNBC: "snap five day losing streak as Iran vows it will not surrender"). İstemde eğilim yoktu. |
| Etki abartılıyor | C1 (gerçek 0,8-1,5x, tahmin >3x) | Savunulabilir: dünya durumu "bir aydır ateş yok" diyor, yani savaşın durumunu değiştiren bir olay gibi okundu. |
| Kategori hatası | H4 "diger", H13 "talep_makro" (ihracat yasağı), C1 savaş/sevkiyat turdan tura değişiyor | |
| Kaynak hatası | H13 OilPrice.com "ana_akim" | |
| Gerekçede piyasa açık/kapalı yanlış | C1, C3, H6, H12, H13 (38 analizin 5'i) | Açık piyasada "açılışta" demek. |
| Uydurma olay numarası | H12 (E24, E26, E29; istemde 8 olay var) | Canlıda yanlış haberlere "bağlantılı" diye gösterilebilirdi. |

Not: 23 Eylül'de Brent +%3,9, WTI −%2,6. WTI'deki düşüş vade geçişinden kaynaklanıyor (Ekim kontratı 22 Eylül'de bitti). H4 etiketi Brent ve CNBC atfıyla geçerli.

**v2.1 değişiklikleri (yalnızca Şubat-Ağustos örneklerine dayanır, Eylül başlığı içermez)**
- **Kategori referansları:**
  - Savaş: savaşın durumunu değiştiren olay ~3,5x, aynı türden tekrar saldırı ~1x (17 Mart: 0,9x).
  - Altyapı: tek tesis ~1x, boğazı atlatan ihracat güzergâhı (Fujairah, 1,7x) ya da ilk kez vurulan ülke (Kuveyt, 2,8x) daha büyük.
  - Diplomasi ilerleme: büyük gücün baskısı (Pakistan/Çin, 24 Temmuz: 1,8x) ve arzı açma teklifi (27 Mayıs: 1,8x).
  - Diplomasi çıkmazı: teklif reddi (29 Nisan: 2,4x).
- **İstem:**
  - Söylem = bilinen tutumun tekrarı. Yeni tutum, şartlı açılma teklifi ve büyük güç baskısı söylem değildir.
  - Büyüklük ile kesinlik ayrı tutulur. Bu kural `beklenen_etki` tanımına da yazıldı.
  - Piyasa kapalıyken "açılış" denir, açıkken denmez.
  - Uzman siteler ve toplayıcılar (OilPrice.com vb.) zayıf kaynaktır.
- **Fiyat eğilimi (D maddesinin bir parçası; bulgu 3.6):** MARKET'e son 5 seansın Brent/WTI hareketleri eklendi (`petrol/regime.py`). Olay günü dahil değil, test edildi.
- **Kod:** İstemde olmayan olay numaraları atılıyor (`keep_known_related`).
- **Testler:** 44 birim testi geçiyor. Yeni korumalar için yapılan 2 mutasyonun ikisini de testler yakaladı.

**Eylül'de hedefli kontrol (örneklem içi, tek tur, kanıt değil)**

| Vaka | v2 (2 tur) | v2.1 |
|---|---|---|
| C8 boru hattı kapandı | 🟡 56 / 49, normal | 🔴 71, büyük |
| C7 "anlaşma aramıyorum" | 📋 10 / 10 | 🟡 35, büyük (hâlâ "söylem") |
| H4 "teslim olmayız" | 📋 0 / 8 | 🟡 35, büyük, yön doğru |
| H3 şartlı Hürmüz teklifi | 🟡 35 / 📋 15 | 🟡 37, büyük |
| H1 Çin'in İran'a baskısı | 📋 15 / 8 | 📋 17 (düzelmedi) |
| C1 ABD saldırısı (orta) | 🔴 81 / 81 | 🔴 86 (aşırı tahmin sürüyor) |
| H11 SPR (zayıf) | 📋 28 / 26 | 📋 28 (aşırı düzeltme yok) |

H1 hâlâ "İran uyar mı belirsiz, etki sınırlı" diyordu. Bu yüzden büyüklük/kesinlik kuralı `beklenen_etki` tanımına da eklendi. Bu son değişiklik henüz hiç çalıştırılmadı.

**Bağımsız doğrulama: Ekim seti (`arastirma/backtest/vakalar_ekim.json`)**
- **İçerik:** 4-9 Ekim'den 14 vaka ve 6 kontrol. v2.1 yazıldıktan sonra, hiçbir model çalıştırılmadan önce etiketlendi.
- **Dağılım:** 1 güçlü, 7 orta, 6 zayıf. Atfı tartışmalı 4 vaka `belirsiz` diye işaretli.
- **Kaynak dosyalar:** Arşiv `haberler_ekim.json`, fiyatlar `gunluk_bz_cl_ekim.csv` ve `ekim_15m_bz_cl.csv`, başlangıç dünya durumu `dunya_durumu_2026-10-03.md`.
- **Ne ölçer:** Hafta sakin geçtiği için set daha çok yanlış alarmı ve aşırı düzeltmeyi ölçer. Lider söylemi, havalimanı saldırısı ve rezerv haberleri buraya girer.
- **Karşılaştırma:** v2 ile v2.1 aynı vakalarda çalıştırılacak. v2 istemi üretim koduna dokunmadan bir betikle geri yükleniyor. Ekim sonuçlarına bakılarak istem değiştirilmeyecek.
- **Sınırlama:** Backtest, olaydan önceki gün içi fiyatı vermiyor (canlıda veriliyor). Bu iki sürümü eşit etkiler.

## 8. Sonraki adımlar

1. ~~A + B + C~~ uygulandı ve Eylül testinden geçti (7.1).
2. ~~Beyan ve altyapı düzeltmeleri~~ v2.1'de yapıldı (7.2).
3. Ekim setinde v2 ile v2.1'i karşılaştırmak (Groq bütçesi açılınca, ~120K token).
4. v2.1'i Eylül'ün tamamında iki tur çalıştırmak (örneklem içi; neyi bozduğunu görmek için).
5. Gölge modda canlı veri toplayıp etiketleri otomatik biriktirmek. Her yeni hafta yeni bir bağımsız test seti demek.
