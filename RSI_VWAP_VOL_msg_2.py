import pandas as pd
import yfinance as yf
import numpy as np
import time
import requests
import os

# ================= Configuration =================
TICKERS_FILE = "your_file.csv"
TELEGRAM_BOT_TOKEN = "8382011014:AAHnGQifO3-XbdC40zJcPjEizqFLIDxp6bY"
TELEGRAM_CHAT_ID = "8398305736"
RISK_REWARD = 2
STOP_BUFFER = 0.005
RSI_PERIOD = 14
VOLUME_MULTIPLIER = 1
INTERVAL_SECONDS = 900  # 15 min
STATUS_INTERVAL_SECONDS = 3600 # 1 hour for status update
TELEGRAM_TOGGLE_FILE = "telegram_toggle.txt"

# Backtesting Configuration (Naya)
RUN_BACKTEST = False # True karein backtest chalane ke liye, False karein live trading ke liye
BACKTEST_PERIOD = "1y" # Jaise ki "1mo", "6mo", "1y", "5y"

# ================= Helper Functions =================
def is_telegram_enabled():
    """Check karein ki telegram messages on hain ya off."""
    try:
        if os.path.exists(TELEGRAM_TOGGLE_FILE):
            with open(TELEGRAM_TOGGLE_FILE, 'r') as f:
                setting = f.read().strip().lower()
                return setting == 'on'
        return True # Default roop se messages on rakhein
    except Exception as e:
        print(f"File reading error: {e}")
        return True # Error aane par bhi messages on rakhein

def send_telegram(message):
    if not is_telegram_enabled():
        print("Telegram messages off hain, message nahi bheja gaya.")
        return

    # Telegram API ko sahi tarike se call karein
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Sahi key 'text' ka upyog karein
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

def vwap(df):
    p = (df['High'] + df['Low'] + df['Close']) / 3
    q = df['Volume']
    return (p * q).cumsum() / q.cumsum()

def rsi(series, period=RSI_PERIOD):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.rolling(period, min_periods=1).mean()
    ma_down = down.rolling(period, min_periods=1).mean()
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

# ================= Backtesting Function (Naya) =================
def run_backtest(tickers, period):
    print(f"Backtesting shuru ho raha hai, period: {period}")
    send_telegram(f"Backtesting shuru ho raha hai, period: {period}")
    all_trades = pd.DataFrame(columns=["Stock","Direction","Entry","Exit","PnL","Duration"])

    for ticker in tickers:
        try:
            data = yf.Ticker(ticker).history(period=period, interval="15m", auto_adjust=False)
            if data.empty:
                continue

            data["VWAP"] = vwap(data)
            data["RSI"] = rsi(data["Close"])
            data["VolumeAvg"] = data["Volume"].rolling(20, min_periods=1).mean()

            in_trade = False
            entry_price = 0
            entry_time = None
            direction = ""

            for i in range(len(data)):
                current_row = data.iloc[i]

                if not in_trade:
                    # Long Signal
                    if (current_row["Close"] > current_row["VWAP"]) and (current_row["RSI"] < 30) and (current_row["Volume"] > VOLUME_MULTIPLIER * current_row["VolumeAvg"]):
                        in_trade = True
                        entry_price = current_row["Close"]
                        entry_time = current_row["Datetime"]
                        direction = "Long"

                    # Short Signal
                    elif (current_row["Close"] < current_row["VWAP"]) and (current_row["RSI"] > 70) and (current_row["Volume"] > VOLUME_MULTIPLIER * current_row["VolumeAvg"]):
                        in_trade = True
                        entry_price = current_row["Close"]
                        entry_time = current_row["Datetime"]
                        direction = "Short"
                else:
                    # Trade Exit Condition (Next signal of opposite direction)
                    if (direction == "Long" and current_row["Close"] < current_row["VWAP"]) or \
                       (direction == "Short" and current_row["Close"] > current_row["VWAP"]):
                        pnl = (current_row["Close"] - entry_price) if direction == "Long" else (entry_price - current_row["Close"])
                        trade_duration = current_row["Datetime"] - entry_time
                        
                        trade_data = pd.DataFrame([{
                            "Stock": ticker,
                            "Direction": direction,
                            "Entry": entry_price,
                            "Exit": current_row["Close"],
                            "PnL": pnl,
                            "Duration": trade_duration
                        }])
                        all_trades = pd.concat([all_trades, trade_data], ignore_index=True)
                        in_trade = False
        
        except Exception as e:
            print(f"Backtesting Error for {ticker}: {e}")
    
    # Backtesting results ka analysis
    total_trades = len(all_trades)
    winning_trades = len(all_trades[all_trades["PnL"] > 0])
    winning_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
    total_pnl = all_trades["PnL"].sum()
    
    # Calculate Max Drawdown
    cumulative_pnl = all_trades["PnL"].cumsum()
    max_drawdown = (cumulative_pnl.cummax() - cumulative_pnl).max()

    results_summary = {
        "Total Trades": total_trades,
        "Winning Trades": winning_trades,
        "Winning Rate (%)": f"{winning_rate:.2f}%",
        "Total PnL": total_pnl,
        "Max Drawdown": max_drawdown
    }

    results_df = pd.DataFrame([results_summary])
    
    print("\nBacktest Results Summary:")
    print(results_df)

    # Results ko Excel aur CSV file mein save karein
    try:
        all_trades.to_csv("backtest_trades.csv", index=False)
        results_df.to_csv("backtest_results.csv", index=False)
        with pd.ExcelWriter("backtest_results.xlsx") as writer:
            all_trades.to_excel(writer, sheet_name="Trades", index=False)
            results_df.to_excel(writer, sheet_name="Summary", index=False)
        print("\nBacktest data successfully saved to backtest_trades.csv and backtest_results.xlsx")
        send_telegram("Backtesting poora ho gaya hai. Results files mein hain.")
    except Exception as e:
        print(f"File save karne mein galti: {e}")


# ================= Main Logic =================
# Tickers aur file variables ko yahan define karein, taaki woh dono modes mein upyog ho sakein.
tickers = pd.read_csv(TICKERS_FILE)["Symbol"].dropna().unique().tolist()
trade_log_file = "real_time_trade_log.csv"

if RUN_BACKTEST:
    # Agar RUN_BACKTEST True hai, to backtest chalao
    run_backtest(tickers, BACKTEST_PERIOD)
else:
    # Varna live monitoring loop chalao
    # Create CSV if not exists
    if not os.path.exists(trade_log_file):
        pd.DataFrame(columns=["Stock","Direction","Entry","SL","Target","Result","Entry Time"]).to_csv(trade_log_file, index=False)

    # Code shuru hote hi "Hello" ka message bhejein
    send_telegram("Code ne kaam karna shuru kar diya hai. Hello!")
    print("Hello message sent. Starting monitoring loop.")

    # Status update ke liye time ko track karein
    last_status_time = time.time()

    # Poore loop ko try...finally block mein daalein
    try:
        while True:
            for ticker in tickers:
                try:
                    data = yf.Ticker(ticker).history(period="2d", interval="15m", auto_adjust=False)
                    if data.empty:
                        continue
                    data = data.dropna().reset_index()
                    data["VWAP"] = vwap(data)
                    data["RSI"] = rsi(data["Close"])
                    data["VolumeAvg"] = data["Volume"].rolling(20, min_periods=1).mean()

                    last_row = data.iloc[-1]
                    entry_time = last_row["Datetime"]

                    # Long signal
                    if (last_row["Close"] > last_row["VWAP"]) and (last_row["RSI"] < 30) and (last_row["Volume"] > VOLUME_MULTIPLIER * last_row["VolumeAvg"]):
                        entry = last_row["Close"]
                        sl = last_row["VWAP"] * (1 - STOP_BUFFER)
                        risk = entry - sl
                        target = entry + risk * RISK_REWARD
                        msg = f"LONG Signal: {ticker}\nEntry: {entry:.2f}\nSL: {sl:.2f}\nTarget: {target:.2f}\nTime: {entry_time}"
                        print(msg)
                        send_telegram(msg)
                        # Append to CSV
                        trade_log = pd.read_csv(trade_log_file)
                        trade_log = pd.concat([trade_log, pd.DataFrame([{"Stock":ticker,"Direction":"Long","Entry":entry,"SL":sl,"Target":target,"Result":None,"Entry Time":entry_time}])], ignore_index=True)
                        trade_log.to_csv(trade_log_file, index=False)

                    # Short signal
                    elif (last_row["Close"] < last_row["VWAP"]) and (last_row["RSI"] > 70) and (last_row["Volume"] > VOLUME_MULTIPLIER * last_row["VolumeAvg"]):
                        entry = last_row["Close"]
                        sl = last_row["VWAP"] * (1 + STOP_BUFFER)
                        risk = sl - entry
                        target = entry - risk * RISK_REWARD
                        msg = f"SHORT Signal: {ticker}\nEntry: {entry:.2f}\nSL: {sl:.2f}\nTarget: {target:.2f}\nTime: {entry_time}"
                        print(msg)
                        send_telegram(msg)
                        # Append to CSV
                        trade_log = pd.read_csv(trade_log_file)
                        trade_log = pd.concat([trade_log, pd.DataFrame([{"Stock":ticker,"Direction":"Short","Entry":entry,"SL":sl,"Target":target,"Result":None,"Entry Time":entry_time}])], ignore_index=True)
                        trade_log.to_csv(trade_log_file, index=False)

                except Exception as e:
                    print(f"{ticker} Error: {e}")

            # Har ghante ek status update message bhejein
            if (time.time() - last_status_time) >= STATUS_INTERVAL_SECONDS:
                send_telegram("Code is still running. Status update!")
                print("Status update message sent.")
                last_status_time = time.time()

            time.sleep(INTERVAL_SECONDS)  # 15 minutes
    finally:
        # Jab code band ho, "Stop" ka message bhejein
        send_telegram("Code ne kaam karna band kar diya hai. Stop!")
        print("Stop message sent. Script terminated.")
