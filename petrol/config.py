import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("PETROL_DATA_DIR", r"C:\PetrolData"))
DB_PATH = DATA_DIR / "petrol.db"

USER_AGENT = "Mozilla/5.0 (compatible; petrol-monitor/0.1)"
POLL_INTERVAL_SEC = 60

# Baslik benzerligi yalnizca neredeyse ayni basliklari birlestirir (olcum: dogru ve yanlis
# birlesmeler 83-91 araliginda ic ice). Anlamsal eslestirmeyi 20b filtresi yapar.
DEDUPE_THRESHOLD = 92
DEDUPE_SHORT_THRESHOLD = 95  # 4 kelimeden kisa basliklar icin daha siki
DEDUPE_WINDOW_HOURS = 12

PRICE_SYMBOLS = {"BZ=F": "Brent", "CL=F": "WTI"}
# 'Normal gun' = son VOL_WINDOW_DAYS islem gununun medyan |gunluk hareket|i; veri yoksa varsayilan
VOL_WINDOW_DAYS = 20
DEFAULT_NORMAL_MOVE_PCT = 2.0
# Modele baglam olarak verilen son seans sayisi (baskin anlati / fiyat egilimi)
TREND_SESSIONS = 5
DAILY_REFRESH_HOURS = 3

# --- AI (OpenAI uyumlu herhangi bir saglayici; prototipte Groq) ---
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY")
TRIAGE_MODEL = os.getenv("TRIAGE_MODEL", "openai/gpt-oss-20b")
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL", "openai/gpt-oss-120b")
TRIAGE_REASONING = os.getenv("TRIAGE_REASONING", "low")
ANALYSIS_REASONING = os.getenv("ANALYSIS_REASONING", "medium")
# Ana modelin gunluk kotasi biterse analiz durmasin diye yedek (bos birakilirsa yedek yok)
ANALYSIS_FALLBACK_MODEL = os.getenv("ANALYSIS_FALLBACK_MODEL", TRIAGE_MODEL)
# Olay birlestirme: 20b bunu filtreyle ayni cagrida yaparken basarisiz oldu; ayri, odakli cagri
MERGE_MODEL = os.getenv("MERGE_MODEL", ANALYSIS_MODEL)
# Siniflandirma isi: dusuk sicaklik ayni habere ayni cevabi verme olasiligini artirir
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
MAX_LLM_ATTEMPTS = 3            # bir habere/olaya kac kez AI denemesi yapilir (hiz siniri sayilmaz)
# Groq ucretsiz plan: model basina gunluk 200K token; payi asmamak icin biraz altinda dur
DAILY_TOKEN_BUDGET = int(os.getenv("DAILY_TOKEN_BUDGET", "190000"))

TRIAGE_BATCH = 20
TRIAGE_MAX_AGE_HOURS = 12      # daha eski haberler filtreye hic gonderilmez
ANALYZE_MIN_IMPORTANCE = 3     # 20b'nin 1-5 onem puani; altindakiler derin analize girmez
ANALYZE_MAX_AGE_HOURS = 12
ANALYZE_PER_CYCLE = 5

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORLD_STATE_PATH = PROJECT_DIR / "dunya_durumu.md"
# Gecmis haber-fiyat tepkilerinden cikarilan referans; varsa analiz istemine eklenir
CALIBRATION_PATH = PROJECT_DIR / "kalibrasyon.md"

# --- Skor ve bildirim seviyeleri (golge modda ayarlanacak) ---
# Esikler veriye gore ayarlanmadi, model v2 katsayilarindan turetildi (analyze.py):
#  kirmizi = buyuk etki (0.85) x ana akim kaynak (0.95) x somut eylem (1.0) x yeni (1.0) x guven 75  ~ 60
#  sari    = normal etki (0.6) x ana akim (0.95) x gelisme raporu (0.85) x yeni x guven 70            ~ 34
LEVEL_RED = 60
LEVEL_YELLOW = 35
PRICED_IN_PCT = 1.0            # haberden beri bu kadar % ayni yonde hareket = "fiyata yansimis"
MARKET_STALE_MIN = 20          # son fiyat bundan eskiyse piyasa kapali sayilir


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    # Genel (petrole ozel olmayan) kaynaklarda anahtar kelime on filtresi uygulanir
    prefilter: bool = False


def _google_news(name: str, query: str) -> Feed:
    q = quote(f"{query} when:1h")
    return Feed(name, f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")


FEEDS: list[Feed] = [
    _google_news("gn_oil", "oil prices OR crude OR Brent OR WTI"),
    _google_news("gn_opec", "OPEC OR Aramco OR \"oil production\" OR \"oil output\""),
    _google_news("gn_supply", "Hormuz OR \"oil pipeline\" OR refinery OR tanker OR \"oil sanctions\""),
    _google_news("gn_war", "Iran OR Israel OR Russia OR Ukraine ceasefire OR war OR peace talks oil"),
    _google_news("gn_trump", "Trump oil OR energy OR OPEC OR Iran OR sanctions"),
    Feed("aljazeera", "https://www.aljazeera.com/xml/rss/all.xml", prefilter=True),
    Feed("bbc_business", "https://feeds.bbci.co.uk/news/business/rss.xml", prefilter=True),
    Feed("anadolu_world", "https://www.aa.com.tr/en/rss/default?cat=world", prefilter=True),
    Feed("oilprice", "https://oilprice.com/rss/main"),
    Feed("eia", "https://www.eia.gov/rss/todayinenergy.xml"),
    Feed("cnbc_energy", "https://www.cnbc.com/id/19836768/device/rss/rss.html"),
]

# Genel kaynaklar icin genis on filtre; asil eleme sonraki asamada 20b modelinde yapilir
PREFILTER_RE = re.compile(
    r"\b(oil|crude|brent|wti|opec|aramco|petrol|gasoline|diesel|fuel|energy|gas|lng|pipeline|"
    r"refiner\w*|tanker|hormuz|barrel|drilling|shale|sanction\w*|embargo|tariff\w*|"
    r"iran\w*|iraq\w*|saudi|russia\w*|ukrain\w*|israel\w*|gaza|houthi\w*|red sea|"
    r"ceasefire|truce|war|peace|opec\+|export\w*|supply|trump|fed|inflation)\b",
    re.IGNORECASE,
)
