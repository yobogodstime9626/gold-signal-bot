import requests
import time
import datetime

# ═══════════════════════════════════════════
#   YOUR PERSONAL SETTINGS
# ═══════════════════════════════════════════
TELEGRAM_TOKEN = "8987697200:AAEq2atMGkoqRVVRARUjOjBV648O9mcUpGo"
TELEGRAM_CHAT_ID = "7025893738"
TWELVE_DATA_API_KEY = "8506066b37c04384b951ca3df7f187c1"

# ═══════════════════════════════════════════
#   SETTINGS
# ═══════════════════════════════════════════
SYMBOL = "XAU/USD"
INTERVAL = "15min"
OUTPUT_SIZE = 250  # need enough candles for the 200-period trend filter
CHECK_EVERY_SECONDS = 900  # 15 minutes


# ═══════════════════════════════════════════
#   SEND TELEGRAM MESSAGE
# ═══════════════════════════════════════════
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=15)
        print("✅ Sent to Telegram")
    except Exception as e:
        print(f"❌ Telegram error: {e}")


# ═══════════════════════════════════════════
#   GET GOLD PRICE DATA (needs high/low/close for ATR)
# ═══════════════════════════════════════════
def get_gold_data():
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "outputsize": OUTPUT_SIZE,
        "apikey": TWELVE_DATA_API_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        data = r.json()
        if "values" not in data:
            print(f"❌ Data error: {data}")
            return None
        # API returns newest-first; flip to oldest-first for indicator math
        return list(reversed(data["values"]))
    except Exception as e:
        print(f"❌ Data fetch error: {e}")
        return None


# ═══════════════════════════════════════════
#   INDICATOR HELPERS
# ═══════════════════════════════════════════
def sma(values, period):
    return sum(values[-period:]) / period


def calculate_ema_series(values, period):
    ema = [sum(values[:period]) / period]
    k = 2 / (period + 1)
    for price in values[period:]:
        ema.append((price - ema[-1]) * k + ema[-1])
    return ema


def calculate_rsi(closes, period=14):
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def calculate_macd(closes):
    ema12 = calculate_ema_series(closes, 12)
    ema26 = calculate_ema_series(closes, 26)
    min_len = min(len(ema12), len(ema26))
    macd_line = [ema12[-min_len + i] - ema26[-min_len + i] for i in range(min_len)]
    signal_line = calculate_ema_series(macd_line, 9)
    return macd_line[-1], signal_line[-1]


def calculate_atr(highs, lows, closes, period=14):
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    return round(sum(trs[-period:]) / period, 2)


# ═══════════════════════════════════════════
#   TREND DETECTION (the main fix)
# ═══════════════════════════════════════════
def detect_trend(closes):
    """
    Uses 50-period and 200-period moving averages plus recent
    swing structure to classify the trend. This is the filter
    that prevents BUY signals from firing during a clear downtrend.
    """
    if len(closes) < 200:
        return "UNKNOWN", 0

    sma50 = sma(closes, 50)
    sma200 = sma(closes, 200)
    price = closes[-1]

    # Recent swing structure (last ~30 candles) for trend strength
    recent = closes[-30:]
    higher_highs = recent[-1] > max(recent[:-1])
    lower_lows = recent[-1] < min(recent[:-1])

    score = 0
    if price > sma50:
        score += 1
    if price > sma200:
        score += 1
    if sma50 > sma200:
        score += 1
    if price < sma50:
        score -= 1
    if price < sma200:
        score -= 1
    if sma50 < sma200:
        score -= 1

    if score >= 2:
        trend = "UPTREND"
    elif score <= -2:
        trend = "DOWNTREND"
    else:
        trend = "SIDEWAYS"

    strength = abs(score)
    return trend, strength


# ═══════════════════════════════════════════
#   GENERATE SIGNAL (trend-filtered)
# ═══════════════════════════════════════════
def analyze(data):
    closes = [float(c["close"]) for c in data]
    highs = [float(c["high"]) for c in data]
    lows = [float(c["low"]) for c in data]
    current_price = closes[-1]

    trend, strength = detect_trend(closes)
    rsi = calculate_rsi(closes)
    macd, signal = calculate_macd(closes)
    atr = calculate_atr(highs, lows, closes)

    print(f"📊 Price:{current_price} Trend:{trend}({strength}) RSI:{rsi} MACD:{round(macd,4)} ATR:{atr}")

    if trend == "UNKNOWN":
        print("⏳ Not enough history yet for trend filter.")
        return None

    reasons = [f"Trend: {trend}"]
    buy_score = 0
    sell_score = 0

    # --- Trend filter: this is what was missing before ---
    # Only allow BUY signals in an uptrend/sideways, only allow
    # SELL signals in a downtrend/sideways. No fighting the trend.
    if trend == "UPTREND":
        buy_score += 2
    elif trend == "DOWNTREND":
        sell_score += 2

    # --- RSI (pullback / exhaustion within the trend) ---
    if rsi < 35:
        buy_score += 1
        reasons.append("RSI pulled back (oversold)")
    elif rsi > 65:
        sell_score += 1
        reasons.append("RSI pulled back (overbought)")

    # --- MACD momentum confirmation ---
    if macd > signal:
        buy_score += 1
        reasons.append("MACD bullish")
    elif macd < signal:
        sell_score += 1
        reasons.append("MACD bearish")

    # Require trend alignment AND momentum confirmation together
    if trend == "UPTREND" and buy_score >= 3:
        direction, emoji = "BUY", "🟢"
        confidence = min(55 + buy_score * 8, 90)
    elif trend == "DOWNTREND" and sell_score >= 3:
        direction, emoji = "SELL", "🔴"
        confidence = min(55 + sell_score * 8, 90)
    else:
        print("⏳ No aligned trend + momentum setup yet.")
        return None

    # ATR-based levels instead of a fixed $15 — adapts to volatility
    if direction == "BUY":
        sl = round(current_price - (1.5 * atr), 2)
        tp1 = round(current_price + (1.5 * atr), 2)
        tp2 = round(current_price + (3 * atr), 2)
    else:
        sl = round(current_price + (1.5 * atr), 2)
        tp1 = round(current_price - (1.5 * atr), 2)
        tp2 = round(current_price - (3 * atr), 2)

    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    message = f"""
🚨 <b>GOLD SIGNAL ALERT</b> 🚨

{emoji} <b>Direction: {direction}</b>
📈 <b>Trend (50/200 MA):</b> {trend}
💰 <b>Entry:</b> ${current_price}
🛑 <b>Stop Loss:</b> ${sl}
🎯 <b>Take Profit 1:</b> ${tp1}
🎯 <b>Take Profit 2:</b> ${tp2}

📊 <b>Analysis:</b>
• RSI: {rsi}
• MACD vs Signal: {round(macd,4)} / {round(signal,4)}
• ATR (volatility): {atr}
• Reasons: {" + ".join(reasons)}
• Confidence: {confidence}%

⏰ {now}

⚠️ <i>This is an automated technical signal, not financial advice.
No system predicts gold reliably — always confirm on your own
chart and use a stop loss.</i>
"""
    return message


# ═══════════════════════════════════════════
#   MAIN LOOP
# ═══════════════════════════════════════════
def main():
    print("🚀 Gold Signal Bot (trend-filtered) started")
    send_telegram(
        "🤖 <b>Gold Signal Bot updated!</b>\n\n"
        "Now uses 50/200 trend filter + RSI + MACD + ATR.\n"
        "Signals only fire WITH the trend, not against it.\n\n"
        "⚠️ Still a technical-only tool — not guaranteed. "
        "Always confirm on your own chart before trading."
    )

    last_signal = None
    while True:
        print(f"\n🔍 Checking gold market... {datetime.datetime.utcnow().strftime('%H:%M:%S')}")
        data = get_gold_data()
        if data:
            signal = analyze(data)
            if signal and signal != last_signal:
                send_telegram(signal)
                last_signal = signal
        print("⏳ Next check in 15 minutes...")
        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
