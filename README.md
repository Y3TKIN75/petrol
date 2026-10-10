# PETROL — Petrol Haber Takip Uygulaması

> **Son güncelleme:** 10 Ekim 2026

---

## 1. Bu proje ne yapıyor?

Petrol fiyatını etkileyebilecek haberleri **otomatik olarak toplar**, yapay zekâ ile **"bu haber petrolü yukarı mı, aşağı mı iter?"** diye değerlendirir ve önemli olanlar için **uyarı verir**.

- 📰 Haberleri toplar (Google News, Al Jazeera, BBC, OilPrice vb.)
- 💹 Brent ve WTI petrol fiyatlarını takip eder
- 🤖 Yapay zekâ (Groq) haberleri filtreler ve analiz eder
- 🚦 Sonucu üç seviyede gösterir: 🔴 acil · 🟡 dikkat · 📋 günlük özet

> ⚠️ Bu proje **bilgilendirme amaçlıdır**, yatırım tavsiyesi değildir.

---

## 2. Şu anki durum (kısaca)

| Durum | Ne? |
|---|---|
| ✅ Hazır | Haber toplama, tekrar eden haberleri birleştirme, yapay zekâ analizi, uyarı seviyeleri, geriye dönük test (backtest) altyapısı |
| 🟡 Yarım | Analiz modeli (v2 ve v2.1). Eylül'de test edildi, Ekim'de henüz test edilmedi |
| ❌ Çalışmıyor | Canlı sistem: **3 Ekim'den beri çalışmıyor** (Groq günlük kotası doldu, bazı kütüphaneler eksik) |
| ⬜ Henüz yok | Telefon uygulaması (PWA) ve telefon bildirimleri |

---

## 3. Şimdiye kadar yapılanlar

### 📅 3 Ekim 2026
- ✅ Haber toplama sistemi kuruldu (5 Google News sorgusu + 6 haber kaynağı)
- ✅ Petrol fiyatları (Brent, WTI) toplanmaya başlandı
- ✅ Aynı haberin tekrar gelmesini engelleyen sistem eklendi
- ✅ Yapay zekâ ile haber filtresi (`gpt-oss-20b`) ve derin analiz (`gpt-oss-120b`) kuruldu
- ✅ 🔴 / 🟡 / 📋 uyarı seviyeleri eklendi
- ✅ **Lider beyanı kuralı** eklendi: Trump gibi liderlerin sözleri en az 🟡 olur, ama bağlama göre 🔴'ye de çıkabilir
- ✅ `dunya_durumu.md` dosyası eklendi: yapay zekâya "şu an dünyada ne oluyor" bilgisini verir
- ✅ Şubat–Ağustos 2026 arasındaki **70 büyük fiyat hareketi** tek tek incelendi ve etiketlendi
- ✅ **Model v2** yazıldı: haber kategorileri, oynaklığa göre büyüklük, yeni eşikler
- ✅ Brent hareketi **WTI ile doğrulanır** hale getirildi (Yahoo'nun Brent verisi bazen hatalı çıkıyor)
- ✅ Elle yapılan analizleri sisteme aktarma komutu eklendi

### 📅 10 Ekim 2026
- ✅ **Eylül testi** yapıldı (19 haber vakası, iki tur):
  - Tüm vakalar filtreden geçti (önceden 15/19)
  - Yön tahmini 18–19 / 19 doğru
  - İlk kez 🔴 uyarılar üretildi
- ✅ **Model v2.1** yazıldı: yapay zekânın hatalarını düzeltmek için istem (prompt) ve kurallar güncellendi
- ✅ **Ekim bağımsız test seti** hazırlandı: 14 haber vakası + 6 kontrol haberi. Etiketler, model çalıştırılmadan **önce** yapıldı
- ✅ 44 otomatik test yazıldı (10 Ekim'de geçtiği kaydedildi)

---

## 4. Yapılması gerekenler

Öncelik sırasına göre. Tamamlananları `[x]` ile işaretleyebilirsin.

### 🔴 Öncelik 1: Sistemi tekrar çalıştır
- [ ] Eksik kütüphaneleri kur: `python -m pip install -r requirements.txt`
  *(feedparser, rapidfuzz ve pytest şu an bilgisayarda yüklü değil)*
- [ ] Groq günlük kotasının yenilendiğini kontrol et *(ücretsiz planda 120b modeli için günlük ~190K token sınırı var)*

### 🟠 Öncelik 2: Ekim testini tamamla
- [ ] Model v2 ile v2.1'i Ekim setinde karşılaştır *(yaklaşık 120K token harcar)*
- [ ] Lider beyanı vakalarını yeniden çalıştır *(Trump'ın "başkan" olduğu düzeltmesi henüz test edilmedi)*
- [ ] ⚠️ **Kural:** Ekim sonuçlarına bakarak istemi değiştirme. Yoksa test sonucu güvenilmez olur

### 🟡 Öncelik 3: Model iyileştirme
- [ ] Somut olmayan açıklamaları daha doğru değerlendir *(Trump "anlaşma aramıyorum", İran "teslim olmayız" gibi)*
- [ ] Altyapı saldırılarını (boru hattı kapanması gibi) daha yüksek seviyede göster
- [ ] Test vakası sayısını 50'nin üzerine çıkar *(Temmuz–Ağustos'taki sert hareketler kullanılabilir)*
- [ ] **Gölge mod:** Canlı sinyalleri gerçek fiyat hareketiyle eşleştirip kaydet. Böylece test verisi kendiliğinden birikir

### 🟢 Öncelik 4: Telefon uygulaması ve bildirim
- [ ] Telefonda çalışan uygulama (PWA) yap
- [ ] HTTPS kur *(Tailscale ile planlandı)*
- [ ] Web Push ile telefona bildirim gönder
- [ ] Telefon tipini belirle (iPhone mu, Android mi?) → **senin kararın gerekiyor**

### 🔵 Öncelik 5: Güvenlik ve düzen
- [ ] `groq_api_key.txt` dosyasını `.gitignore`'a ekle, ya da anahtarı sadece `.env` dosyasında tut
- [ ] `.env` dosyasını hiç kimseyle paylaşma
- [ ] Yeni haber kaynakları ekle *(Çin hükümeti haberleri, ABD Enerji Bakanlığı açıklamaları)*

---

## 5. Projeyi nasıl çalıştırırım?

**Adım 1 — Kütüphaneleri kur** (proje klasöründe):
```bash
python -m pip install -r requirements.txt
```

**Adım 2 — API anahtarını ayarla:** `.env.example` dosyasını kopyalayıp `.env` adını ver ve içine Groq anahtarını yaz:
```
GROQ_API_KEY=buraya_anahtarin
```

**Adım 3 — Komutlar:**

| Komut | Ne yapar? |
|---|---|
| `python -m petrol collect --once` | Sadece haberleri ve fiyatları toplar (AI kullanmaz) |
| `python -m petrol run --once` | Toplar + AI ile filtreler ve analiz eder |
| `python -m petrol signals` | Son uyarıları listeler |
| `python -m petrol report` | Kaynak, hacim ve AI kullanım raporunu gösterir |
| `python -m pytest` | Otomatik testleri çalıştırır |

> 💡 `backtest` komutları Groq kotasını harcar. Önce kotanın durumuna bak.

---

## 6. Klasörler ne işe yarıyor?

| Klasör / Dosya | İçeriği |
|---|---|
| `petrol/` | Programın kendisi (toplama, analiz, uyarı kodları) |
| `tests/` | Otomatik testler |
| `arastirma/` | Araştırma notları, geçmiş veriler, test vakaları |
| `arastirma/backtest/` | Geriye dönük test vakaları ve sonuçları |
| `arastirma/veri/` | Ham fiyat ve haber verileri |
| `dunya_durumu.md` | Yapay zekânın bilmesi gereken güncel dünya durumu. Elle güncellenir |
| `C:\PetrolData\` | Veritabanı (`petrol.db`) ve günlük dosyaları. OneDrive dışında tutulur |

---

## 7. Önemli uyarılar

- ⚠️ **Yatırım tavsiyesi değildir.** Bu uygulama bilgi ve takip içindir.
- ⚠️ **Brent verisi güvenilir değil.** Yahoo'nun Brent gün içi verisi bazen iki farklı vadeyi karıştırıyor. Bu yüzden Brent hareketi, WTI ile aynı yöndeyse kabul ediliyor.
- ⚠️ **Yapay zekâ hata yapabilir.** Yön tahmini genelde doğru çıkıyor, ama uyarı seviyeleri (🔴/🟡) henüz tam güvenilir değil.
- ⚠️ **Test sonuçları küçük örneklere dayanıyor.** Sonuçlar kesin değil, yönlendirici.
- ⚠️ **Groq kotası sınırlı.** Günlük token bitince analiz yavaşlar veya durur.

---

## 8. Sözlük (kısa terimler)

| Terim | Anlamı |
|---|---|
| **Brent / WTI** | İki önemli ham petrol türü ve fiyat göstergesi |
| **Vadeli kontrat** | İleri bir tarihte teslim edilecek petrolün fiyatı. Vade değişince fiyat "sıçrayabilir" |
| **RSS** | Haber sitelerinin yeni yazıları otomatik paylaşma biçimi |
| **Token** | Yapay zekâya gönderilen ve alınan metnin ölçü birimi. Ücretsiz planda sınırlıdır |
| **Backtest (geriye dönük test)** | Geçmiş bir olayda sistemin ne diyeceğini kontrol etme |
| **Vaka / Kontrol** | Vaka: fiyatı etkilediği bilinen haber. Kontrol: etkisi olmayan haber (yanlış alarm ölçmek için) |
| **Bağımsız test seti** | Model ayarlanırken hiç görülmemiş, dürüst ölçüm için ayrılan haberler |
| **Gölge mod** | Sistemin sonuç üretip kullanıcıya göstermeden, sadece kaydettiği deneme modu |
| **PWA** | Tarayıcıda çalışan ama telefona uygulama gibi yüklenebilen web sayfası |
