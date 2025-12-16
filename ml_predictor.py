#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML-Powered Advanced Trading Strategy
Uses 90+ indicators from CSV data to predict BUY/SELL signals
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime
import pickle
import warnings
warnings.filterwarnings('ignore')

# Fix encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

print("=" * 80)
print("🧠 ML-POWERED TRADING BOT - ADVANCED BACKTESTING")
print("90+ Indicators | 6 Years Data | Machine Learning")
print("=" * 80)

# ============================================================================
# CONFIGURATION
# ============================================================================

CSV_PATH = r"C:\Users\Adem\Desktop\binance_veri\analizli_veri\BTCUSDT_15m.csv"
TRAIN_TEST_SPLIT = 0.8  # 80% train, 20% test
INITIAL_BALANCE = 1000
TRADE_AMOUNT = 50
STOP_LOSS = 0.03  # 3%
TAKE_PROFIT = 0.06  # 6%

# ============================================================================
# LOAD DATA
# ============================================================================

print("\n📂 Loading CSV data...")
df = pd.read_csv(CSV_PATH, parse_dates=['date'])
print(f"   ✅ Loaded {len(df):,} rows ({df['date'].min()} to {df['date'].max()})")
print(f"   📊 Price range: ${df['Close'].min():.2f} - ${df['Close'].max():.2f}")

# ============================================================================
# FEATURE ENGINEERING
# ============================================================================

print("\n🔧 Feature Engineering...")

# Select relevant features (remove OHLCV and date)
feature_cols = [col for col in df.columns if col not in ['date', 'Open', 'High', 'Low', 'Close', 'Volume']]
print(f"   ✅ Using {len(feature_cols)} features (indicators)")

# Create target: Future price movement
# 1 = Price will go up (BUY signal)
# 0 = Price will go down (SELL signal)
df['future_return'] = df['Close'].pct_change().shift(-1)  # Next candle's return
df['target'] = (df['future_return'] > 0).astype(int)

# Fill NaN with forward fill, then backward fill
df_clean = df.fillna(method='ffill').fillna(method='bfill')

# Remove any remaining NaN rows
df_clean = df_clean.dropna()
print(f"   ✅ Cleaned data: {len(df_clean):,} rows")

# ============================================================================
# PREPARE TRAIN/TEST SPLIT
# ============================================================================

split_idx = int(len(df_clean) * TRAIN_TEST_SPLIT)
train_df = df_clean.iloc[:split_idx]
test_df = df_clean.iloc[split_idx:]

print(f"\n📊 Data Split:")
print(f"   Train: {len(train_df):,} rows ({train_df['date'].min()} to {train_df['date'].max()})")
print(f"   Test:  {len(test_df):,} rows ({test_df['date'].min()} to {test_df['date'].max()})")

X_train = train_df[feature_cols]
y_train = train_df['target']
X_test = test_df[feature_cols]
y_test = test_df['target']

# ============================================================================
# TRAIN MULTIPLE MODELS
# ============================================================================

print("\n🤖 Training ML Models...")

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

models = {
    'Random Forest': RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1),
    'Gradient Boosting': GradientBoostingClassifier(n_estimators=100, max_depth=5, random_state=42),
    'Logistic Regression': LogisticRegression(max_iter=1000, random_state=42)
}

results = {}

for name, model in models.items():
    print(f"\n   Training {name}...")
    model.fit(X_train, y_train)

    # Predictions
    y_pred = model.predict(X_test)

    # Metrics
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)

    results[name] = {
        'model': model,
        'accuracy': accuracy,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'predictions': y_pred
    }

    print(f"   ✅ {name}:")
    print(f"      Accuracy:  {accuracy:.2%}")
    print(f"      Precision: {precision:.2%}")
    print(f"      Recall:    {recall:.2%}")
    print(f"      F1 Score:  {f1:.2%}")

# Select best model (highest F1 score)
best_model_name = max(results, key=lambda k: results[k]['f1'])
best_model = results[best_model_name]['model']
print(f"\n🏆 Best Model: {best_model_name} (F1: {results[best_model_name]['f1']:.2%})")

# ============================================================================
# BACKTESTING WITH ML PREDICTIONS
# ============================================================================

print("\n📈 Backtesting with ML predictions...")

test_df = test_df.copy()
test_df['ml_prediction'] = results[best_model_name]['predictions']

# Simulate trading
balance = INITIAL_BALANCE
positions = []
trades = []
winning_trades = 0
losing_trades = 0

for i in range(len(test_df)):
    row = test_df.iloc[i]
    current_price = row['Close']
    ml_signal = row['ml_prediction']

    # Check for exits (SL/TP)
    closed_positions = []
    for pos in positions:
        # LONG position
        sl_price = pos['entry'] * (1 - STOP_LOSS)
        tp_price = pos['entry'] * (1 + TAKE_PROFIT)

        if current_price <= sl_price:
            # Stop Loss hit
            pnl = (sl_price - pos['entry']) * pos['qty']
            balance += pos['cost'] + pnl
            trades.append({'type': 'LONG', 'entry': pos['entry'], 'exit': sl_price, 'pnl': pnl, 'result': 'LOSS'})
            losing_trades += 1
            closed_positions.append(pos)
        elif current_price >= tp_price:
            # Take Profit hit
            pnl = (tp_price - pos['entry']) * pos['qty']
            balance += pos['cost'] + pnl
            trades.append({'type': 'LONG', 'entry': pos['entry'], 'exit': tp_price, 'pnl': pnl, 'result': 'WIN'})
            winning_trades += 1
            closed_positions.append(pos)

    # Remove closed positions
    for pos in closed_positions:
        positions.remove(pos)

    # Open new positions based on ML signal
    if ml_signal == 1 and len(positions) == 0 and balance >= TRADE_AMOUNT:
        # BUY signal
        qty = TRADE_AMOUNT / current_price
        positions.append({
            'entry': current_price,
            'qty': qty,
            'cost': TRADE_AMOUNT
        })
        balance -= TRADE_AMOUNT

# Close remaining positions at market
for pos in positions:
    current_price = test_df.iloc[-1]['Close']
    pnl = (current_price - pos['entry']) * pos['qty']
    balance += pos['cost'] + pnl
    trades.append({'type': 'LONG', 'entry': pos['entry'], 'exit': current_price, 'pnl': pnl, 'result': 'WIN' if pnl > 0 else 'LOSS'})
    if pnl > 0:
        winning_trades += 1
    else:
        losing_trades += 1

# ============================================================================
# RESULTS
# ============================================================================

total_trades = winning_trades + losing_trades
win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
total_pnl = balance - INITIAL_BALANCE
total_return = (total_pnl / INITIAL_BALANCE) * 100

print("\n" + "=" * 80)
print("📊 BACKTEST RESULTS")
print("=" * 80)
print(f"\n💰 Financial Performance:")
print(f"   Initial Balance:  ${INITIAL_BALANCE:,.2f}")
print(f"   Final Balance:    ${balance:,.2f}")
print(f"   Total P&L:        ${total_pnl:+,.2f}")
print(f"   Total Return:     {total_return:+.2f}%")

print(f"\n📈 Trading Performance:")
print(f"   Total Trades:     {total_trades}")
print(f"   Winning Trades:   {winning_trades}")
print(f"   Losing Trades:    {losing_trades}")
print(f"   Win Rate:         {win_rate:.2f}%")

if trades:
    avg_win = np.mean([t['pnl'] for t in trades if t['result'] == 'WIN']) if winning_trades > 0 else 0
    avg_loss = np.mean([t['pnl'] for t in trades if t['result'] == 'LOSS']) if losing_trades > 0 else 0
    print(f"\n💵 P&L Analysis:")
    print(f"   Avg Win:   ${avg_win:+.2f}")
    print(f"   Avg Loss:  ${avg_loss:+.2f}")
    if avg_loss != 0:
        print(f"   Win/Loss:  {abs(avg_win/avg_loss):.2f}x")

# ============================================================================
# FEATURE IMPORTANCE
# ============================================================================

if hasattr(best_model, 'feature_importances_'):
    print("\n🔍 TOP 10 MOST IMPORTANT INDICATORS:")
    print("-" * 80)

    importances = pd.DataFrame({
        'feature': feature_cols,
        'importance': best_model.feature_importances_
    }).sort_values('importance', ascending=False)

    for i, row in importances.head(10).iterrows():
        print(f"   {row['feature'][:40]:40s} | {row['importance']:.4f}")

# ============================================================================
# SAVE MODEL
# ============================================================================

print("\n💾 Saving ML model...")
model_path = 'ml_model.pkl'
with open(model_path, 'wb') as f:
    pickle.dump({
        'model': best_model,
        'model_name': best_model_name,
        'features': feature_cols,
        'metrics': results[best_model_name]
    }, f)
print(f"   ✅ Model saved to: {model_path}")

print("\n" + "=" * 80)
print("✅ BACKTESTING COMPLETE!")
print("=" * 80)
