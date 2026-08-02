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
  market_data/       # Piyasa sınıfları + mum modelleri, CSV yükleyici, depo
  indicators/        # SMA, EMA, RSI, MACD, ATR
  strategies/        # Strateji arayüzü + teknik analiz stratejileri
  signals/           # SignalEngine: stratejileri ağırlıklı birleştirme
  risk/              # Risk limitleri ve pozisyon boyutlandırma
  portfolio/         # Paper portföy modeli (nakit, pozisyon, düşüş takibi)
  execution/         # Güvenlik + risk + broker + portföyü bağlayan motor
  brokers/           # Broker arayüzü + paper broker (stub)
  backtest/          # Paper-only backtest motoru (strateji + sonuç metrikleri)
  paper_trading/     # Paper-only orchestrator (SignalEngine -> ExecutionEngine)
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

### Mum verisi modelleri ve yükleme

- `BarSeries` — tek bir sembole ait, zamana göre sıralı ve doğrulanmış OHLCV
  mum serisi (OHLC tutarlılığı, pozitif fiyat, artan zaman damgası kontrolü).
  `closes`, `highs`, `lows`, `opens`, `volumes` özellikleriyle `numpy` dizileri
  sunar.
- `Timeframe` — zaman dilimleri (`1m`, `5m`, `15m`, `1h`, `4h`, `1d`, `1w`).
- `load_bars_from_csv(path, symbol, allowed_root=..., timeframe=...)` —
  `timestamp,open,high,low,close,volume` sütunlu CSV'den `BarSeries` yükler.
  Dosya yalnızca `allowed_root` altında okunur; path traversal, symlink kaçışı,
  duplicate timestamp ve sırasız CSV güvenli şekilde reddedilir.
- `InMemoryBarRepository` — serileri sembol + zaman dilimine göre saklar;
  `get_range(...)` ile tarih aralığı sorgusu yapılır.

## 🔁 Backtest

`app.backtest` altında **paper-only** geçmişe dönük sınama motoru:

- `BacktestEngine(strategy, config=...)` — bir stratejiyi `BarSeries` üzerinde
  mum-mum çalıştırır. İşlemler yerleşik `PaperBroker` + `ExecutionEngine`
  üzerinden yürütülür; risk limitleri ve paper-only güvenceler backtest'te de
  geçerlidir (gerçek emir gönderimi yok).
- `BacktestConfig` — `initial_cash`, `stop_loss_pct` (pozisyon boyutlandırma),
  `warmup`.
- `BacktestResult` — özkaynak eğrisi, işlemler ve özet metrikler:
  `total_return`, `max_drawdown`, `num_trades`.

```python
from app.backtest import BacktestEngine
from app.market_data import load_bars_from_csv, Timeframe
from app.strategies import SMACrossoverStrategy

series = load_bars_from_csv("aapl.csv", "AAPL", allowed_root="data", timeframe=Timeframe.D1)
result = BacktestEngine(SMACrossoverStrategy()).run(series)
print(result.total_return, result.max_drawdown, result.num_trades)
```

## 🧭 Stratejiler ve sinyal motoru

### Sinyal modeli

`app.strategies.base.Signal` immutable bir teknik analiz sinyalidir:

- `type` — `BUY` / `SELL` / `HOLD`
- `strength` — 0 ile 1 arası güven; NaN/inf veya aralık dışı değerler reddedilir
- `reason` — açıklama, `strategy` — üreten stratejinin adı, `timestamp`, `symbol`

`Strategy` arayüzünün sözleşmesi: yalnızca geçmiş ve mevcut kapanışları alır
(gelecek barlara erişim yok → **look-ahead bias yok**), `min_bars` ile gereken
asgari bar sayısını bildirir, yetersiz veride `HOLD` döndürür ve aynı girdi için
**deterministik** aynı sonucu üretir.

### Stratejiler

| Strateji | Sınıf | Sinyal mantığı |
|----------|-------|----------------|
| SMA kesişim | `SMACrossoverStrategy` | Kısa SMA uzun SMA'yı keser |
| EMA kesişim | `EMACrossoverStrategy` | Kısa EMA uzun EMA'yı keser |
| RSI | `RSIStrategy` | Aşırı satım → BUY, aşırı alım → SELL |
| MACD kesişim | `MACDCrossoverStrategy` | Histogram işaret değiştirir |
| Trend + RSI | `TrendRSIStrategy` | Trend filtresi + RSI zamanlaması |

Her strateji parametrelerini doğrular, NaN/inf girdiyi güvenli şekilde `HOLD`
ile karşılar ve deterministiktir.

### SignalEngine

`app.signals.SignalEngine` bir veya birden fazla stratejiyi çalıştırıp
sonuçlarını **ağırlıklı** birleştirir. Ağırlıklar pozitif, sonlu ve toplamı
sıfırdan büyük olmalıdır. Çelişkili sinyallerde ya da yapılandırılabilir
`min_strength` eşiğinin altında güvenli şekilde `HOLD` döner. Kill switch
etkinse daima `HOLD` döner. **Hiçbir emir göndermez** — yalnızca sinyal üretir.

```python
from app.signals import SignalEngine
from app.strategies import EMACrossoverStrategy, RSIStrategy

engine = SignalEngine(
    [EMACrossoverStrategy(12, 26), RSIStrategy(14)],
    weights=[2.0, 1.0],
    min_strength=0.3,
)
combined = engine.evaluate("AAPL", closes)
print(combined.signal.type, combined.signal.strength, combined.net_score)
```

## 📝 Paper trading orchestrator (paper-only)

`app.paper_trading.PaperTradingOrchestrator` bir `BarSeries` üzerinde bar-by-bar
çalışır: her barda `SignalEngine` sinyalini üretir ve kararı **bir sonraki barın
açılış (open) fiyatında** `ExecutionEngine` üzerinden gerçekleştirir. Böylece
look-ahead bias oluşmaz.

Güvenceler: yalnızca yerleşik `PaperBroker` kullanılır; global kill switch ve
mevcut `RiskManager` uygulanır; short selling kapalıdır; yetersiz nakit ve fazla
satış reddedilir. Komisyon ve slippage yapılandırılabilir.

```python
from app.paper_trading import PaperTradingOrchestrator, OrchestratorConfig
from app.signals import SignalEngine
from app.strategies import SMACrossoverStrategy

engine = SignalEngine([SMACrossoverStrategy(20, 50)])
orch = PaperTradingOrchestrator(
    engine, OrchestratorConfig(initial_cash=100_000, commission_rate=0.001, slippage_rate=0.0005)
)
result = orch.run(series)  # series: app.market_data.BarSeries
print(result.final_equity, result.num_accepted, result.num_rejected)
```

`PaperTradingResult`: üretilen sinyaller, kabul/ret edilen emirler ve red
nedenleri, final nakit/equity, pozisyonlar ve equity curve.

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
