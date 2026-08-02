# esiyat-robot

Yatırım robotunun ilk **güvenli backend iskeleti**. Python 3.12 + FastAPI ile
kurulmuştur. Bu sürüm bilinçli olarak **yalnızca paper trading** yapar; gerçek
emir gönderimi kod seviyesinde kapalıdır.

## 🔒 Güvenlik kuralları (zorunlu)

Bu kurallar yapılandırma ile gevşetilemez; kod seviyesinde zorlanır:

- **Paper trading varsayılan ve zorunludur.** `TRADING_MODE` yalnızca `paper`
  kabul eder; başka bir değer verilse bile güvenli tarafa (`paper`) çekilir.
- **Gerçek emir gönderimi kapalıdır.** `LIVE_TRADING_DISABLED` daima `True`
  olur; `ExecutionEngine` yalnızca `is_paper=True` olan broker'ları kabul eder.
- **Hiçbir API anahtarı veya gizli bilgi commit edilmez.** `.env` dosyası
  `.gitignore` ile dışlanmıştır; yalnızca `.env.example` paylaşılır.
- **Broker entegrasyonu yalnızca arayüz/stub seviyesindedir.** Gerçek broker
  bağlantısı yoktur; canlı piyasa verisi de bağlı değildir.

## 📁 Proje yapısı

```
app/
  main.py            # FastAPI giriş noktası + başlangıç güvenlik doğrulaması
  api/               # HTTP yönlendiricileri (/health, /safety, kill switch)
  core/              # Yapılandırma (config) ve kill switch
  market_data/       # BIST, ABD hisseleri ve altın piyasa sınıfları (stub)
  indicators/        # SMA, EMA, RSI, MACD, ATR
  strategies/        # Strateji arayüzü + örnek SMA kesişim stratejisi
  risk/              # Risk limitleri ve pozisyon boyutlandırma
  portfolio/         # Paper portföy modeli (nakit, pozisyon, düşüş takibi)
  execution/         # Güvenlik + risk + broker + portföyü bağlayan motor
  brokers/           # Broker arayüzü + paper broker (stub)
tests/               # pytest test paketi
```

## 📊 Göstergeler

`app.indicators` altında saf, `numpy` tabanlı fonksiyonlar:

- `sma` — Basit Hareketli Ortalama
- `ema` — Üstel Hareketli Ortalama
- `rsi` — Göreceli Güç Endeksi (Wilder)
- `macd` — MACD çizgisi, sinyal ve histogram
- `atr` — Ortalama Gerçek Aralık (Wilder)

## 🏦 Piyasalar

`app.market_data` altında sembol normalizasyonu ve para birimi kurallarıyla:

- `BISTMarket` — Borsa İstanbul (TRY, `THYAO.IS` biçimi)
- `USEquityMarket` — ABD hisseleri (USD)
- `GoldMarket` — Altın/emtia (`XAUUSD`, `XAUTRY`)

Canlı veri erişimi bilinçli olarak `NotImplementedError` yükseltir.

## ⚖️ Risk limitleri

| Kural | Varsayılan |
|-------|-----------|
| İşlem başına azami risk | %1 |
| Tek varlık azami ağırlığı | %10 |
| Günlük azami zarar | %3 |
| Portföy azami düşüşü | %10 |

`RiskManager` her işlemi bu limitlere ve **kill switch** durumuna göre değerlendirir.

## 🛑 Kill switch

`app.core.kill_switch.kill_switch` süreç içi ve ortam değişkeni bayraklarını
birleştirir. Etkinken hiçbir emir (paper dahil) işlenmez. HTTP üzerinden
`POST /safety/kill-switch` ile yönetilir.

## 🚀 Kurulum ve çalıştırma

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Ortam değişkenlerini hazırlayın (gizli bilgileri asla commit etmeyin)
cp .env.example .env

# Uygulamayı başlatın
uvicorn app.main:app --reload
```

Sağlık kontrolü:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/safety
```

## 🧪 Geliştirme

```bash
ruff check app tests        # lint
ruff format app tests       # biçimlendirme
mypy app                    # tip denetimi
pytest                      # testler
```

## 🐳 Docker

```bash
docker build -t esiyat-robot .
docker run -p 8000:8000 esiyat-robot
```

Konteyner kök olmayan kullanıcı ile çalışır ve `TRADING_MODE=paper`,
`LIVE_TRADING_DISABLED=true` ile başlatılır.

## 🔁 CI

`.github/workflows/ci.yml`; her push ve `main`'e açılan PR'da ruff (lint +
format), mypy ve pytest çalıştırır.

## ⚠️ Sorumluluk reddi

Bu proje eğitim/iskelet amaçlıdır ve yatırım tavsiyesi değildir. Gerçek emir
gönderimi bu sürümde bilinçli olarak devre dışıdır.
