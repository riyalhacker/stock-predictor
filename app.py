from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
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
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import os

def clean_stock_symbol(stock):
    stock = stock.upper()
    if ".NS" not in stock:
        stock += ".NS"
    return stock

# ---------------- APP CONFIG ----------------
app = Flask(__name__)

# IMPORTANT: Allows your Vercel frontend to talk to this Render backend
CORS(app, resources={r"/*": {"origins": "*"}})

# Optimized for the Gunicorn Gevent worker on Render
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# ---------------- DATABASE ----------------
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "stocks.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = "supersecretkey"

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# ---------------- MODELS ----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    balance = db.Column(db.Float, default=1000000.0)

class Portfolio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    stock = db.Column(db.String(20), nullable=False)
    shares = db.Column(db.Integer, nullable=False)

with app.app_context():
    db.create_all()

# ---------------- LIVE MARKET STREAM ----------------
def stream_stock_data():
    stocks = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "TATAMOTORS.NS"]
    while True:
        data = {}
        for s in stocks:
            try:
                ticker = yf.Ticker(s)
                # fast_info is efficient for live price
                price = ticker.fast_info['last_price']
                data[s] = round(float(price), 2)
            except:
                continue
        socketio.emit("market_update", data)
        time.sleep(5)

# Run market stream in background
threading.Thread(target=stream_stock_data, daemon=True).start()

# ---------------- ROUTES ----------------

@app.route('/')
def home():
    return "Stock Predictor Backend is Running!"

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"message": "User already exists"}), 400
    hashed_pw = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    new_user = User(username=data['username'], password=hashed_pw)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"message": "User registered"}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data['username']).first()
    if user and bcrypt.check_password_hash(user.password, data['password']):
        token = create_access_token(identity=user.username)
        return jsonify(access_token=token)
    return jsonify({"message": "Invalid credentials"}), 401

@app.route('/predict', methods=['GET'])
def predict():
    stock = request.args.get('stock', 'RELIANCE.NS')
    stock = clean_stock_symbol(stock)
    try:
        df = yf.download(stock, period="1y", interval="1d")
        if df.empty: return jsonify({"error": "No data"}), 404
        
        df['S_10'] = df['Close'].rolling(window=10).mean()
        df['Corr'] = df['Close'].rolling(window=10).corr(df['S_10'])
        df = df.dropna()
        
        X = df[['S_10', 'Corr']]
        y = df['Close']
        split = int(0.8 * len(df))
        model = LinearRegression().fit(X[:split], y[:split])
        
        current_price = float(df['Close'].iloc[-1])
        predicted_price = float(model.predict(X.tail(1))[0])
        
        return jsonify({
            "stock": stock,
            "current": round(current_price, 2),
            "predicted": round(predicted_price, 2),
            "advice": "BUY" if predicted_price > current_price else "SELL"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/backtest', methods=['GET'])
def backtest():
    stock = request.args.get('stock', 'RELIANCE.NS')
    stock = clean_stock_symbol(stock)
    try:
        data = yf.download(stock, period="1y", interval="1d")
        data['SMA_20'] = data['Close'].rolling(window=20).mean()
        data['SMA_50'] = data['Close'].rolling(window=50).mean()
        data = data.dropna()

        balance = 1000000
        shares = 0
        trades = []

        for i in range(len(data)):
            price = float(data['Close'].iloc[i])
            date = str(data.index[i].date())
            
            # Simple SMA Crossover Strategy
            if data['SMA_20'].iloc[i] > data['SMA_50'].iloc[i] and shares == 0:
                shares = balance // price
                balance -= shares * price
                trades.append({"type": "BUY", "price": round(price, 2), "date": date})
            elif data['SMA_20'].iloc[i] < data['SMA_50'].iloc[i] and shares > 0:
                balance += shares * price
                shares = 0
                trades.append({"type": "SELL", "price": round(price, 2), "date": date})

        final_val = balance + (shares * float(data['Close'].iloc[-1]))
        return jsonify({
            "initial": 1000000,
            "final": round(final_val, 2),
            "profit": round(final_val - 1000000, 2),
            "trades": trades
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/news', methods=['GET'])
def get_news():
    feed = feedparser.parse("https://finance.yahoo.com/rss/topstories")
    news = []
    for entry in feed.entries[:5]:
        sentiment = "Positive" if TextBlob(entry.summary).sentiment.polarity > 0 else "Negative"
        news.append({"title": entry.title, "link": entry.link, "sentiment": sentiment})
    return jsonify(news)

# ---------------- RUN ----------------
if __name__ == '__main__':
    # Render assigns a dynamic port via environment variables
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)