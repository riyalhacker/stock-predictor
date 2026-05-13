from flask import Flask, request, jsonify,render_template
from flask_cors import CORS

from flask_socketio import (
    SocketIO,
    emit
)

import threading
import time

import yfinance as yf
import pandas as pd
import numpy as np

from sklearn.linear_model import LinearRegression

import feedparser
from textblob import TextBlob

from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt

from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt_identity
)
def clean_stock_symbol(stock):

    stock = stock.upper()

    if ".NS" not in stock:

        stock += ".NS"

    return stock

# ---------------- APP ----------------
app = Flask(__name__)

CORS(app)

socketio = SocketIO(

    app,

    cors_allowed_origins="*"
)

# ---------------- DATABASE ----------------
app.config[
    "SQLALCHEMY_DATABASE_URI"
] = "sqlite:///stocks.db"

app.config[
    "SQLALCHEMY_TRACK_MODIFICATIONS"
] = False

app.config[
    "JWT_SECRET_KEY"
] = "supersecretkey"

db = SQLAlchemy(app)

bcrypt = Bcrypt(app)

jwt = JWTManager(app)

# ---------------- USER MODEL ----------------
class User(db.Model):

    id = db.Column(

        db.Integer,

        primary_key=True
    )

    username = db.Column(

        db.String(100),

        unique=True,

        nullable=False
    )

    password = db.Column(

        db.String(200),

        nullable=False
    )

# ---------------- STORAGE ----------------
portfolio = []

paper_balance = 1000000

paper_holdings = []

# ---------------- NEWS ----------------
def get_stock_news(stock):

    try:

        url = (

            f"https://news.google.com/rss/search?q={stock}+stock"
        )

        feed = feedparser.parse(url)

        news_list = []

        for entry in feed.entries[:5]:

            title = entry.title

            sentiment = TextBlob(
                title
            ).sentiment.polarity

            if sentiment > 0:

                label = "Bullish"

            elif sentiment < 0:

                label = "Bearish"

            else:

                label = "Neutral"

            news_list.append({

                "title":
                    title,

                "sentiment":
                    label,

                "score":
                    round(sentiment, 2)
            })

        return news_list

    except:

        return []

# ---------------- PATTERN ----------------
def detect_pattern(df):

    try:

        last = df.iloc[-1]

        prev = df.iloc[-2]

        open_price = float(last["Open"])

        close_price = float(last["Close"])

        high_price = float(last["High"])

        low_price = float(last["Low"])

        prev_open = float(prev["Open"])

        prev_close = float(prev["Close"])

        body = abs(
            close_price - open_price
        )

        candle_range = (
            high_price - low_price
        )

        upper_shadow = (

            high_price -

            max(
                open_price,
                close_price
            )
        )

        lower_shadow = (

            min(
                open_price,
                close_price
            ) - low_price
        )

        if body < candle_range * 0.1:

            return (

                "Doji ⚖️",

                "Market indecision"
            )

        elif (

            lower_shadow > body * 2

            and

            upper_shadow < body
        ):

            return (

                "Hammer 🔨",

                "Possible bullish reversal"
            )

        elif (

            upper_shadow > body * 2

            and

            lower_shadow < body
        ):

            return (

                "Shooting Star ☄️",

                "Possible bearish reversal"
            )

        elif (

            prev_close < prev_open

            and

            close_price > open_price

            and

            close_price > prev_open

            and

            open_price < prev_close
        ):

            return (

                "Bullish Engulfing 🔥",

                "Strong bullish reversal"
            )

        elif (

            prev_close > prev_open

            and

            close_price < open_price

            and

            open_price > prev_close

            and

            close_price < prev_open
        ):

            return (

                "Bearish Engulfing 🩸",

                "Strong bearish reversal"
            )

        return (

            "No Major Pattern",

            "Neutral"
        )

    except:

        return (

            "Unknown",

            "No pattern detected"
        )

# ---------------- MARKET MOVERS ----------------
def get_market_movers():
    stocks = [
        "RELIANCE.NS",
        "TCS.NS",
        "INFY.NS",
        "HDFCBANK.NS",
        "ICICIBANK.NS",
        "SBIN.NS",
        "ITC.NS",
        "LT.NS"
        ]

    gainers = []

    losers = []

    for stock in stocks:

        try:

            data = yf.download(

                stock,

                period="2d",

                progress=False
            )

            if data.empty:
                continue

            if isinstance(
                data.columns,
                pd.MultiIndex
            ):

                data.columns = [

                    col[0]

                    if isinstance(col, tuple)

                    else col

                    for col in data.columns
                ]

            close_prices = (

                data["Close"]

                .dropna()

                .tolist()
            )

            if len(close_prices) < 2:
                continue

            previous = float(
                close_prices[-2]
            )

            current = float(
                close_prices[-1]
            )

            change = round(

                (
                    (
                        current - previous
                    )

                    / previous
                ) * 100,

                2
            )

            item = {

                "stock":
                    stock,

                "price":
                    round(current, 2),

                "change":
                    change
            }

            if change >= 0:

                gainers.append(item)

            else:

                losers.append(item)

        except:
            pass

    gainers = sorted(

        gainers,

        key=lambda x: x["change"],

        reverse=True
    )

    losers = sorted(

        losers,

        key=lambda x: x["change"]
    )

    return {

        "gainers":
            gainers[:5],

        "losers":
            losers[:5]
    }

# ---------------- LIVE STREAM ----------------
def stream_stock_data():
    tracked_stocks = [
        "RELIANCE.NS",
        "TCS.NS",
        "INFY.NS",
        "HDFCBANK.NS",
        "ICICIBANK.NS"
        ]

    while True:

        live_data = []

        for stock in tracked_stocks:

            try:

                data = yf.download(

                    stock,

                    period="1d",

                    interval="1m",

                    progress=False
                )

                if data.empty:
                    continue

                if isinstance(
                    data.columns,
                    pd.MultiIndex
                ):

                    data.columns = [

                        col[0]

                        if isinstance(col, tuple)

                        else col

                        for col in data.columns
                    ]

                close_prices = (

                    data["Close"]

                    .dropna()

                    .tolist()
                )

                if len(close_prices) < 2:
                    continue

                current_price = round(

                    float(close_prices[-1]),

                    2
                )

                previous_price = round(

                    float(close_prices[-2]),

                    2
                )

                change = round(

                    current_price -

                    previous_price,

                    2
                )

                percent = round(

                    (
                        change /

                        previous_price
                    ) * 100,

                    2
                )

                live_data.append({

                    "stock":
                        stock,

                    "price":
                        current_price,

                    "change":
                        change,

                    "percent":
                        percent
                })

            except:
                pass

        socketio.emit(

            "live_market",

            live_data
        )

        time.sleep(5)

# ---------------- HOME ----------------
@app.route('/')
def home():
    return render_template("index.html")

# ---------------- REGISTER ----------------
@app.route('/register', methods=['POST'])
def register():

    try:

        data = request.json

        username = data["username"]

        password = data["password"]

        existing = User.query.filter_by(

            username=username
        ).first()

        if existing:

            return jsonify({

                "error":
                    "User already exists"
            })

        hashed_password = bcrypt.generate_password_hash(
            password
        ).decode('utf-8')

        user = User(

            username=username,

            password=hashed_password
        )

        db.session.add(user)

        db.session.commit()

        return jsonify({

            "message":
                "User registered successfully"
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        })

# ---------------- LOGIN ----------------
@app.route('/login', methods=['POST'])
def login():

    try:

        data = request.json

        username = data["username"]

        password = data["password"]

        user = User.query.filter_by(

            username=username
        ).first()

        if not user:

            return jsonify({

                "error":
                    "Invalid username"
            })

        if not bcrypt.check_password_hash(

            user.password,

            password
        ):

            return jsonify({

                "error":
                    "Invalid password"
            })

        token = create_access_token(
            identity=username
        )

        return jsonify({

            "token": token,

            "username": username
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        })

# ---------------- PROFILE ----------------
@app.route('/profile')
@jwt_required()
def profile():

    current_user = get_jwt_identity()

    return jsonify({

        "message":
            f"Welcome {current_user}"
    })

# ---------------- PREDICT ----------------
@app.route('/predict')
def predict():

    try:

        stock = clean_stock_symbol(  request.args.get("stock") )

        if not stock:

            return jsonify({
                "error":
                    "No stock provided"
            })

        data = yf.download(

            stock,

            period="3mo",

            progress=False
        )

        if data.empty:

            return jsonify({
                "error":
                    "Invalid stock"
            })

        data.reset_index(inplace=True)

        if isinstance(
            data.columns,
            pd.MultiIndex
        ):

            data.columns = [

                col[0]

                if isinstance(col, tuple)

                else col

                for col in data.columns
            ]

        for col in [

            "Open",
            "High",
            "Low",
            "Close"
        ]:

            data[col] = pd.to_numeric(

                data[col],

                errors="coerce"
            )

        data.dropna(inplace=True)

        if len(data) < 20:

            return jsonify({
                "error":
                    "Not enough data"
            })

        df = pd.DataFrame()

        df["Close"] = data["Close"]

        df["MA5"] = (

            df["Close"]

            .rolling(5)

            .mean()
        )

        df["MA10"] = (

            df["Close"]

            .rolling(10)

            .mean()
        )

        # RSI
        delta = df["Close"].diff()

        gain = delta.where(
            delta > 0,
            0
        )

        loss = -delta.where(
            delta < 0,
            0
        )

        avg_gain = gain.rolling(14).mean()

        avg_loss = loss.rolling(14).mean()

        rs = avg_gain / avg_loss

        df["RSI"] = (

            100 -

            (100 / (1 + rs))
        )

        # MACD
        ema12 = df["Close"].ewm(

            span=12,

            adjust=False

        ).mean()

        ema26 = df["Close"].ewm(

            span=26,

            adjust=False

        ).mean()

        df["MACD"] = ema12 - ema26

        df["Signal_Line"] = df["MACD"].ewm(

            span=9,

            adjust=False

        ).mean()

        df.dropna(inplace=True)

        # AI MODEL
        X = df[["Close", "MA5", "MA10"]]

        y = df["Close"].shift(-1)

        X = X[:-1]

        y = y[:-1]

        model = LinearRegression()

        model.fit(X, y)

        future_predictions = []

        last_price = float(
            df["Close"].iloc[-1]
        )

        volatility = (

            df["Close"]

            .pct_change()

            .std()
        )

        trend_strength = (

            (
                df["Close"].iloc[-1]

                -

                df["MA10"].iloc[-1]
            )

            /

            df["MA10"].iloc[-1]
        )

        for _ in range(7):

            random_change = np.random.normal(

                loc=trend_strength * 0.05,

                scale=volatility * 0.5
            )

            next_price = (

                last_price *

                (1 + random_change)
            )

            future_predictions.append(

                round(
                    float(next_price),
                    2
                )
            )

            last_price = next_price

        # CANDLE DATA
        candles = []

        latest = data.tail(30)

        for _, row in latest.iterrows():

            date_value = pd.to_datetime(
                row["Date"]
            )

            candles.append({

                "x": int(
                    date_value.timestamp() * 1000
                ),

                "y": [

                    round(float(row["Open"]), 2),

                    round(float(row["High"]), 2),

                    round(float(row["Low"]), 2),

                    round(float(row["Close"]), 2)
                ]
            })

        current_price = round(

            float(df["Close"].iloc[-1]),

            2
        )

        previous_price = round(

            float(df["Close"].iloc[-2]),

            2
        )

        change = round(

            current_price -

            previous_price,

            2
        )

        percent_change = round(

            (
                change /

                previous_price
            ) * 100,

            2
        )

        ma10 = round(

            float(df["MA10"].iloc[-1]),

            2
        )

        if current_price > ma10:

            trend = "Uptrend"

            signal = "BUY"

        else:

            trend = "Downtrend"

            signal = "SELL"

        pattern, pattern_desc = detect_pattern(
            data.tail(5)
        )

        news = get_stock_news(stock)

        return jsonify({

            "stock":
                stock.upper(),

            "prediction":
                future_predictions[-1],

            "future_predictions":
                future_predictions,

            "candles":
                candles,
                
            "currency":
                "INR",
            
            "current_price":
                round(current_price, 2),

            "change":
                change,

            "percent_change":
                percent_change,

            "trend":
                trend,

            "signal":
                signal,

            "pattern":
                pattern,

            "pattern_desc":
                pattern_desc,

            "rsi":
                df["RSI"]
                .tail(30)
                .fillna(0)
                .tolist(),

            "macd":
                df["MACD"]
                .tail(30)
                .fillna(0)
                .tolist(),

            "signal_line":
                df["Signal_Line"]
                .tail(30)
                .fillna(0)
                .tolist(),

            "news":
                news
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        })

# ---------------- AI CHAT ----------------
@app.route('/chat')
def chat_ai():

    try:

        stock = request.args.get("stock")

        stock = clean_stock_symbol(stock)

        data = yf.download(

            stock,

            period="3mo",

            progress=False
        )

        if data.empty:

            return jsonify({

                "response":
                    "I could not analyze this stock."
            })

        if isinstance(
            data.columns,
            pd.MultiIndex
        ):

            data.columns = [

                col[0]

                if isinstance(col, tuple)

                else col

                for col in data.columns
            ]

        close = data["Close"]

        ma20 = close.rolling(20).mean().iloc[-1]

        current = close.iloc[-1]

        # RSI
        delta = close.diff()

        gain = delta.where(delta > 0, 0)

        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.rolling(14).mean()

        avg_loss = loss.rolling(14).mean()

        rs = avg_gain / avg_loss

        rsi = (

            100 -

            (100 / (1 + rs.iloc[-1]))
        )

        # MACD
        ema12 = close.ewm(
            span=12,
            adjust=False
        ).mean()

        ema26 = close.ewm(
            span=26,
            adjust=False
        ).mean()

        macd = ema12.iloc[-1] - ema26.iloc[-1]

        # Pattern
        pattern, desc = detect_pattern(
            data.tail(5)
        )

        # News
        news = get_stock_news(stock)

        bullish_news = len([

            n for n in news

            if n["sentiment"] == "Bullish"
        ])

        bearish_news = len([

            n for n in news

            if n["sentiment"] == "Bearish"
        ])

        # AI RESPONSE
        response = f"""

Stock Analysis for {stock}

Current Price: ₹{round(float(current),2)}

Trend:
"""

        if current > ma20:

            response += (
                "The stock is trading above the 20-day moving average, indicating bullish momentum.\n\n"
            )

        else:

            response += (
                "The stock is trading below the 20-day moving average, indicating bearish pressure.\n\n"
            )

        # RSI
        if rsi > 70:

            response += (
                f"RSI is {round(float(rsi),2)}, which suggests the stock may be overbought.\n\n"
            )

        elif rsi < 30:

            response += (
                f"RSI is {round(float(rsi),2)}, which suggests the stock may be oversold.\n\n"
            )

        else:

            response += (
                f"RSI is {round(float(rsi),2)}, showing balanced momentum.\n\n"
            )

        # MACD
        if macd > 0:

            response += (
                "MACD is positive, indicating bullish momentum.\n\n"
            )

        else:

            response += (
                "MACD is negative, indicating bearish momentum.\n\n"
            )

        # Pattern
        response += f"""
Candlestick Pattern:
{pattern} — {desc}

"""

        # News sentiment
        if bullish_news > bearish_news:

            response += (
                "Recent news sentiment appears bullish.\n\n"
            )

        elif bearish_news > bullish_news:

            response += (
                "Recent news sentiment appears bearish.\n\n"
            )

        else:

            response += (
                "Recent news sentiment appears neutral.\n\n"
            )

        # Final verdict
        if (

            current > ma20

            and rsi < 70

            and macd > 0
        ):

            response += (
                "Overall AI outlook: Bullish momentum with potential upside."
            )

        else:

            response += (
                "Overall AI outlook: Mixed or weak momentum. Trade carefully."
            )

        return jsonify({

            "response": response
        })

    except Exception as e:

        return jsonify({

            "response": str(e)
        })

# ---------------- MARKET ----------------
@app.route('/market')
def market():

    return jsonify(
        get_market_movers()
    )

# ---------------- ADD PORTFOLIO ----------------
@app.route('/add', methods=['POST'])
def add_stock():

    try:

        data = request.json

        stock = clean_stock_symbol( data["stock"] )

        shares = float(data["shares"])

        stock_data = yf.download(

            stock,

            period="1d",

            progress=False
        )

        if isinstance(
            stock_data.columns,
            pd.MultiIndex
        ):

            stock_data.columns = [

                col[0]

                if isinstance(col, tuple)

                else col

                for col in stock_data.columns
            ]

        price = round(

            float(
                stock_data["Close"].iloc[-1]
            ),

            2
        )

        portfolio.append({

            "stock":
                stock.upper(),

            "shares":
                shares,
            
            "price":
                round(price, 2),
            
            "currency":
                "INR"
        })

        return jsonify({
            "message":
                "Added"
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        })

# ---------------- PORTFOLIO ----------------
@app.route('/portfolio')
def portfolio_view():

    total = 0

    for item in portfolio:

        total += (

            item["shares"]

            *

            item["price"]
        )

    return jsonify({

        "portfolio":
            portfolio,

        "total_value":
            round(total, 2)
    })

# ---------------- PAPER BUY ----------------
@app.route('/paper-buy', methods=['POST'])
def paper_buy():

    global paper_balance

    try:

        data = request.json

        stock = clean_stock_symbol(data["stock"])

        shares = float(data["shares"])

        stock_data = yf.download(

            stock,

            period="1d",

            progress=False
        )

        if stock_data.empty:

            return jsonify({
                "error":
                    "Invalid stock"
            })

        if isinstance(
            stock_data.columns,
            pd.MultiIndex
        ):

            stock_data.columns = [

                col[0]

                if isinstance(col, tuple)

                else col

                for col in stock_data.columns
            ]

        current_price = round(

            float(
                stock_data["Close"].iloc[-1]
            ),

            2
        )

        total_cost = round(

            current_price * shares,

            2
        )

        if total_cost > paper_balance:

            return jsonify({
                "error":
                    "Not enough balance"
            })

        paper_balance -= total_cost

        found = False

        for item in paper_holdings:

            if item["stock"] == stock:

                item["shares"] += shares

                found = True

                break

        if not found:

            paper_holdings.append({

                "stock":
                    stock,

                "shares":
                    shares,

                "buy_price":
                    current_price
            })

        return jsonify({

            "message":
                "Stock Bought",

            "balance":
                round(paper_balance, 2)
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        })

# ---------------- PAPER SELL ----------------
@app.route('/paper-sell', methods=['POST'])
def paper_sell():

    global paper_balance

    try:

        data = request.json

        stock = clean_stock_symbol( data["stock"])

        shares = float(data["shares"])

        for item in paper_holdings:

            if item["stock"] == stock:

                if shares > item["shares"]:

                    return jsonify({

                        "error":
                            "Not enough shares"
                    })

                stock_data = yf.download(

                    stock,

                    period="1d",

                    progress=False
                )

                if isinstance(
                    stock_data.columns,
                    pd.MultiIndex
                ):

                    stock_data.columns = [

                        col[0]

                        if isinstance(col, tuple)

                        else col

                        for col in stock_data.columns
                    ]

                current_price = round(

                    float(
                        stock_data["Close"].iloc[-1]
                    ),

                    2
                )

                total = round(

                    current_price * shares,

                    2
                )

                item["shares"] -= shares

                paper_balance += total

                if item["shares"] <= 0:

                    paper_holdings.remove(item)

                return jsonify({

                    "message":
                        "Stock Sold",

                    "balance":
                        round(paper_balance, 2)
                })

        return jsonify({
            "error":
                "Stock not found"
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        })

# ---------------- PAPER PORTFOLIO ----------------
@app.route('/paper-portfolio')
def paper_portfolio():

    try:

        total_value = 0

        holdings_data = []

        for item in paper_holdings:

            stock = item["stock"]

            shares = item["shares"]

            buy_price = item["buy_price"]

            stock_data = yf.download(

                stock,

                period="1d",

                progress=False
            )

            if isinstance(
                stock_data.columns,
                pd.MultiIndex
            ):

                stock_data.columns = [

                    col[0]

                    if isinstance(col, tuple)

                    else col

                    for col in stock_data.columns
                ]

            current_price = round(

                float(
                    stock_data["Close"].iloc[-1]
                ),

                2
            )

            total = round(

                current_price * shares,

                2
            )

            profit = round(

                (
                    current_price - buy_price
                ) * shares,

                2
            )

            total_value += total

            holdings_data.append({

                "stock":
                    stock,

                "shares":
                    shares,

                "buy_price":
                    buy_price,

                "current_price":
                    current_price,

                "total":
                    total,

                "profit":
                    profit
            })

        return jsonify({

            "balance":
                round(paper_balance, 2),

            "portfolio_value":
                round(total_value, 2),

            "holdings":
                holdings_data
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        })

# ---------------- CREATE DATABASE ----------------
with app.app_context():

    db.create_all()

# ---------------- START LIVE THREAD ----------------
thread = threading.Thread(

    target=stream_stock_data
)

thread.daemon = True

thread.start()
@app.route('/backtest')
def backtest():

    try:

        stock = clean_stock_symbol(

            request.args.get('stock')
        )

        data = yf.download(

            stock,

            period='6mo',

            progress=False
        )

        if data.empty:

            return jsonify({

                "error":
                    "Invalid stock"
            })

        if isinstance(
            data.columns,
            pd.MultiIndex
        ):

            data.columns = [

                col[0]

                if isinstance(col, tuple)

                else col

                for col in data.columns
            ]

        data['MA5'] = (

            data['Close']
            .rolling(5)
            .mean()
        )

        data['MA20'] = (

            data['Close']
            .rolling(20)
            .mean()
        )

        balance = 1000000

        shares = 0

        trades = []

        for i in range(20, len(data)):

            current_price = float(

                data['Close'].iloc[i]
            )

            ma5 = float(

                data['MA5'].iloc[i]
            )

            ma20 = float(

                data['MA20'].iloc[i]
            )

            date = str(
                data.index[i]
            )

            # BUY
            if ma5 > ma20 and shares == 0:

                shares = (

                    balance /

                    current_price
                )

                balance = 0

                trades.append({

                    "type": "BUY",

                    "price": round(
                        current_price,
                        2
                    ),

                    "date": date
                })

            # SELL
            elif ma5 < ma20 and shares > 0:

                balance = (

                    shares *

                    current_price
                )

                shares = 0

                trades.append({

                    "type": "SELL",

                    "price": round(
                        current_price,
                        2
                    ),

                    "date": date
                })

        final_value = balance

        if shares > 0:

            final_value = (

                shares *

                float(
                    data['Close'].iloc[-1]
                )
            )

        profit = round(

            final_value - 1000000,

            2
        )

        roi = round(

            (
                profit / 1000000
            ) * 100,

            2
        )

        return jsonify({

            "stock":
                stock,

            "currency":
                "INR",

            "initial_balance":
                1000000,

            "final_value":
                round(final_value, 2),

            "profit":
                profit,

            "roi":
                roi,

            "trades":
                trades
        })

    except Exception as e:

        return jsonify({

            "error":
                str(e)
        })
# ---------------- RUN ----------------
if __name__ == '__main__':

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )