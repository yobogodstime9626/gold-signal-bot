import requests
import time
import datetime

# ═══════════════════════════════════════════
#   YOUR PERSONAL SETTINGS
# ═══════════════════════════════════════════
TELEGRAM_TOKEN = "8987697200:AAEq2atMGkoqRVVRARUjOjBV648O9mcUpGo"
TELEGRAM_CHAT_ID = "7025893738"
TWELVE_DATA_API_KEY = "8506066b37c04384b951ca3df7f187c1"  # Replace with your key

# ═══════════════════════════════════════════
#   SETTINGS
# ═══════════════════════════════════════════
SYMBOL = "XAU/USD"
INTERVAL = "15min"
CHECK_EVERY_SECONDS = 900  # Check every 15 minutes


# ═══════════════════════════════════════════
#   SEND TELEGRAM MESSAGE
# ═══════════════════════════════════════════
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload)
        print("✅ Signal sent to Telegram!")
    except Exception as e:
        print(f"❌ Telegram error: {e}")


# ═══════════════════════════════════════════
#   GET GOLD PRICE DATA
# ═══════════════════════════════════════════
def get_gold_data():
    url = f"https://api.twelvedata.com/time_series"
    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "outputsize": 50,
        "apikey": TWELVE_DATA_API_KEY
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if "values" not in data:
            print(f"❌ Data error: {data}")
            return None
        return data["values"]
    except Exception as e:
        print(f"❌ Data fetch error: {e}")
        return None


# ═══════════════════════════════════════════
#   CALCULATE RSI
# ═══════════════════════════════════════════
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


# ═══════════════════════════════════════════
#   CALCULATE MACD
# ═══════════════════════════════════════════
def calculate_ema(closes, period):
    ema = [sum(closes[:period]) / period]
    multiplier = 2 / (period + 1)
    for price in closes[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema


def calculate_macd(closes):
    ema12 = calculate_ema(closes, 12)
    ema26 = calculate_ema(closes, 26)
    min_len = min(len(ema12), len(ema26))
    macd_line = [ema12[-min_len + i] - ema26[-min_len + i] for i in range(min_len)]
    signal_line = calculate_ema(macd_line, 9)
    return macd_line[-1], signal_line[-1]


# ═══════════════════════════════════════════
#   CALCULATE STOP LOSS & TAKE PROFIT
# ═══════════════════════════════════════════
def calculate_levels(price, direction):
    if direction == "BUY":
        sl = round(price - 15, 2)
        tp1 = round(price + 15, 2)
        tp2 = round(price + 30, 2)
    else:
        sl = round(price + 15, 2)
        tp1 = round(price - 15, 2)
        tp2 = round(price - 30, 2)
    return sl, tp1, tp2


# ═══════════════════════════════════════════
#   ANALYZE & GENERATE SIGNAL
# ═══════════════════════════════════════════
def analyze(data):
    closes = [float(candle["close"]) for candle in reversed(data)]
    current_price = closes[-1]

    rsi = calculate_rsi(closes)
    macd, signal = calculate_macd(closes)

    print(f"📊 Price: {current_price} | RSI: {rsi} | MACD: {round(macd,4)} | Signal: {round(signal,4)}")

    reasons = []
    buy_score = 0
    sell_score = 0

    # RSI Logic
    if rsi < 30:
        buy_score += 2
        reasons.append("RSI Oversold")
    elif rsi < 45:
        buy_score += 1
        reasons.append("RSI Bullish Zone")
    elif rsi > 70:
        sell_score += 2
        reasons.append("RSI Overbought")
    elif rsi > 55:
        sell_score += 1
        reasons.append("RSI Bearish Zone")

    # MACD Logic
    if macd > signal:
        buy_score += 2
        reasons.append("MACD Bullish Crossover")
    elif macd < signal:
        sell_score += 2
        reasons.append("MACD Bearish Crossover")

    # Determine direction
    if buy_score >= 3:
        direction = "BUY"
        emoji = "🟢"
        confidence = min(50 + (buy_score * 10), 95)
    elif sell_score >= 3:
        direction = "SELL"
        emoji = "🔴"
        confidence = min(50 + (sell_score * 10), 95)
    else:
        print("⏳ No strong signal yet...")
        return None

    sl, tp1, tp2 = calculate_levels(current_price, direction)
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    message = f"""
🚨 <b>GOLD SIGNAL ALERT</b> 🚨

{emoji} <b>Direction: {direction}</b>
💰 <b>Entry Price:</b> ${current_price}
🛑 <b>Stop Loss:</b> ${sl}
🎯 <b>Take Profit 1:</b> ${tp1}
🎯 <b>Take Profit 2:</b> ${tp2}

📊 <b>Analysis:</b>
• RSI: {rsi}
• MACD: {round(macd, 4)}
• Reason: {" + ".join(reasons)}
• Confidence: {confidence}%

⏰ <b>Time:</b> {now}

⚠️ <i>Always use proper risk management!</i>
"""
    return message


# ═══════════════════════════════════════════
#   MAIN LOOP
# ═══════════════════════════════════════════
def main():
    print("🚀 Gold Signal Bot Started!")
    send_telegram("🤖 <b>Gold Signal Bot is now ACTIVE!</b>\n\nI will send you XAU/USD buy/sell signals every 15 minutes.\n\n⚠️ Always manage your risk on Exness!")

    last_signal = None

    while True:
        print(f"\n🔍 Checking gold market... {datetime.datetime.utcnow().strftime('%H:%M:%S')}")
        data = get_gold_data()

        if data:
            signal = analyze(data)
            if signal and signal != last_signal:
                send_telegram(signal)
                last_signal = signal

        print(f"⏳ Next check in 15 minutes...")
        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
