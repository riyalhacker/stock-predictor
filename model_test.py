import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

# Step 1: Download stock data
data = yf.download("AAPL", start="2020-01-01", end="2024-01-01")

# Step 2: Check if data loaded
if data.empty:
    print("Error: No data fetched. Check internet or stock symbol.")
    exit()

# Step 3: Prepare dataset
data['Prediction'] = data['Close'].shift(-1)

# Features (X) and labels (y)
X = data[['Close']][:-1]
y = data['Prediction'][:-1]

# Step 4: Train model
model = LinearRegression()
model.fit(X, y)

# Step 5: Predict next value (CORRECT SHAPE)
last_price = data[['Close']].iloc[-1].values.reshape(1, -1)
prediction = model.predict(last_price)

# Step 6: Output result
print("Last known price:", data['Close'].iloc[-1])
print("Next predicted price:", prediction[0])