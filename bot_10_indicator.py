#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
10 İNDİKATÖR OYLAMA SİSTEMİ İLE TRADING BOT
3/10 kural: 3 veya daha fazla AL sinyali → LONG, 3 veya daha fazla SAT sinyali → SHORT
"""

import sys
import os
import pandas as pd
import numpy as np
import json
import time
import requests
import csv
from datetime import datetime
from flask import Flask, jsonify
from flask_cors import CORS
import threading
import webbrowser

# ADAPTİF ÖĞRENME SİSTEMİ
from adaptive_learning import (
    analyze_performance,
    update_coin_performance,
    check_coin_blacklist,
    get_learning_metrics
)

# Fix encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# ============================================================================
# CONFIGURATION
# ============================================================================

DEMO_MODE = False
DEMO_BALANCE = 1000  # $1000 başlangıç
TRADE_AMOUNT = 15  # $15 per trade - SABİT TUTAR (DÜŞÜRÜLDÜ: zarar kontrolü)
COMMISSION_RATE = 0.0005  # 0.05% komisyon (Binance futures TAKER fee - gerçek oran)
STOP_LOSS_PERCENT = 0.006  # 0.6% (DÜZELTME: slippage buffer için dar tutuldu)
SLIPPAGE_BUFFER = 0.002  # 0.2% slippage buffer (gerçek max zarar: 0.8%)
TAKE_PROFIT_PERCENT = 0.025  # 2.5% (OPTİMİZE: daha fazla kar)
SCAN_INTERVAL = 2  # 2 saniye (OPTİMİZE: daha hızlı)
MAX_OPEN_POSITIONS = 999  # SINIRSIZ - Para bitene kadar işlem aç
FUTURES_LEVERAGE = 5  # 5x (KULLANICI İSTEĞİ: sabit)
AUTO_START = True  # OTOMATİK BAŞLATMA (Render için gerekli!)

# ADAPTİF ÖĞRENME SİSTEMİ AYARLARI
ADAPTIVE_LEARNING = True  # Öğrenme sistemini aktifleştir
MIN_INDICATOR_VOTES = 3  # Başlangıç değeri (OPTİMİZE: 4→3, daha fazla işlem)
ANALYSIS_INTERVAL = 8  # Her 8 işlemde bir analiz yap (OPTİMİZE: daha sık öğrenme)
COIN_BLACKLIST_HOURS = 12  # Kötü coinler 12 saat kara listede (OPTİMİZE: daha az kısıtlama)
TARGET_WIN_RATE = 0.55  # %55 doğruluk hedefi (OPTİMİZE: daha yüksek hedef)
IDLE_PROFIT_CLOSE_MINUTES = 3  # 3dk işlem yoksa kardakileri kapat (OPTİMİZE: daha hızlı)
IDLE_PROFIT_THRESHOLD = 0.5  # $0.5 ve üzeri kar (OPTİMİZE: küçük karları da al)

# TRAILING TAKE PROFIT AYARLARI
TRAILING_TP_ACTIVATION_PERCENT = 0.04  # %4 kar olunca trailing TP aktif
TRAILING_TP_DISTANCE_PERCENT = 0.01    # Zirveden %1 düşünce kapat

# TRAILING STOP LOSS AYARLARI (KAR KORUMA SİSTEMİ) - v7.2 GERÇEK TRAİLİNG!
TRAILING_SL_ENABLED = True  # Trailing SL aktif (kar edince SL'yi yukarı çek)
TRAILING_SL_MODE = "continuous"  # "continuous" = sürekli takip, "levels" = 3 seviyeli (ESKİ)
TRAILING_SL_DISTANCE_PCT = 0.005  # Zirveden %0.5 uzaklıkta SL (GERÇEK TRAİLİNG)
# ESKİ Sistem (artık kullanılmıyor ama kodda kalacak):
TRAILING_SL_LEVELS = [
    {"profit_pct": 0.005, "sl_pct": 0.000},  # %0.5 karda → SL break-even
    {"profit_pct": 0.010, "sl_pct": 0.003},  # %1.0 karda → SL %0.3 karda
    {"profit_pct": 0.015, "sl_pct": 0.008}   # %1.5 karda → SL %0.8 karda
]

# BREAK-EVEN STOP AYARLARI (5 DAKİKA KURALI) - YENİ!
BREAK_EVEN_ENABLED = True  # Break-even stop aktif (5dk sonra zarar riski sıfır)
BREAK_EVEN_TIME_MINUTES = 5  # 5 dakika bekle
BREAK_EVEN_MIN_PROFIT_PCT = 0.005  # Minimum %0.5 kar

# MARKET TREND VE MOMENTUM ESIKLERI
MARKET_TREND_THRESHOLD = 0.003  # %0.3 market trend eşiği
MOMENTUM_THRESHOLD_PERCENT = 0.001  # %0.1 momentum eşiği
INDICATOR_THRESHOLD_MULTIPLIER = 3.5  # 3.5 threshold çarpanı (SAT sinyalleri için çok daha geniş aralık - SHORT artışı!)

# COOLDOWN (BEKLEME SÜRESİ) ÇARPANLARI - Kötü coinlerden uzak dur (OPTİMİZE)
COOLDOWN_MULTIPLIER = {
    'stop_loss': 2.0,      # Stop loss yiyenlere 2x cooldown (OPTİMİZE: 3→2, daha hızlı)
    'take_profit': 0.5,    # TP alanlara 0.5x cooldown (OPTİMİZE: karlı coinlere hızlı dön)
    'idle_profit': 1.0,    # Idle kapatmalara 1x cooldown (OPTİMİZE: 1.5→1)
    'base_hours': 1        # Base cooldown süresi: 1 saat (OPTİMİZE: 2→1, 2x hızlı)
}

# POZİSYON BÜYÜKLÜĞÜ OPTİMİZASYONU - SABİT (ZARAR KONTROLÜ)
POSITION_SIZING_ENABLED = False  # Dinamik pozisyon büyüklüğü KAPALI (zarar kontrolü için)
POSITION_SIZE_BY_VOTES = {
    10: 50,  # 10/10 oy → $50 (OPTİMİZE: çok güçlü sinyallere MAX para)
    9: 45,   # 9/10 oy → $45
    8: 40,   # 8/10 oy → $40
    7: 35,   # 7/10 oy → $35
    6: 30,   # 6/10 oy → $30
    5: 25,   # 5/10 oy → $25
    4: 20,   # 4/10 oy → $20
    3: 15    # 3/10 oy → $15 (OPTİMİZE: yeni eklendi, minimum)
}

# VOLATİLİTE (OYNAKLIK) FİLTRESİ - Çok durgun veya çok çılgın coinlerden kaçın (OPTİMİZE)
VOLATILITY_FILTER_ENABLED = True  # Volatilite filtresi aktif
MIN_VOLATILITY_24H = 0.3  # Minimum %0.3 24h fiyat değişimi (OPTİMİZE: daha fazla coin)
MAX_VOLATILITY_24H = 20.0  # Maximum %20 24h fiyat değişimi (OPTİMİZE: yüksek volatilite=yüksek kar)

# v7.2: PİYASA TRENDİ ALGILAMA - HIZLI KARAR MERCİSİ!
MARKET_TREND_ENABLED = True  # Market trend algılama aktif
MARKET_TREND_CHECK_INTERVAL = 2  # Her 2 saniyede bir trend güncelle (ULTRA AGRESİF! 5→2)
MARKET_TREND_REFERENCE_COIN = "BTCUSDT"  # BTC ile piyasa trendini ölç
MARKET_TREND_PERIOD = 20  # 20 mumla trend hesapla (HIZLI TEPKIME! 30→20)
MARKET_TREND_LONG_MULTIPLIER = 3.0  # Piyasa yükselişte LONG sinyalleri 3x ağırlıklı
MARKET_TREND_SHORT_MULTIPLIER = 3.0  # Piyasa düşüşte SHORT sinyalleri 3x ağırlıklı

# YENİ FİLTRELER (OPTİMİZE v6.0 - GÜÇLÜ İNDİKATÖRLER)
MIN_24H_VOLUME = 1_000_000  # Minimum 24h hacim: $1M (SHORT artışı için daha fazla coin!)
MIN_VOLATILITY_PERCENT = 0.0015  # Minimum volatilite: ATR > fiyatın %0.15'ü (OPTİMİZE: daha geniş)
MOMENTUM_CHECK_ENABLED = True  # Fiyat yönü doğrulaması (sinyal yönü ile uyumlu olmalı)

# HİBRİT DİNAMİK LİSTE SİSTEMİ (OPTİMİZE v6.0)
DYNAMIC_COIN_LIST = True  # Dinamik coin listesi aktif
FAST_SCAN_INTERVAL = 2  # Her 2 saniyede ana liste taraması (OPTİMİZE: daha hızlı)
FULL_SCAN_INTERVAL = 20  # Her 20 saniyede tüm market taraması (OPTİMİZE: 3x daha sık, 30→20)
SMART_LIMIT_ENABLED = True  # Akıllı limit aktif
SMART_LIMIT_THRESHOLD = 250  # 250+ coin tarama (OPTİMİZE: 200→250, güçlü indikatörlerle daha fazla coin)
PUMP_DETECTION_ENABLED = True  # Pump algılama aktif
PUMP_VOLUME_MULTIPLIER = 5  # 5x hacim artışı = pump
PROTECT_OPEN_POSITIONS = True  # Açık pozisyon varsa listede kal
EXCLUDED_FIAT_PAIRS = ['TRY', 'EUR', 'GBP', 'BRL', 'ARS', 'RUB', 'UAH', 'BIDR', 'AUD', 'NGN', 'PLN', 'RON', 'ZAR', 'VAI']  # Fiat çiftleri hariç

# BAŞLANGIÇ LİSTESİ (İlk çalıştırmada kullanılır, sonra dinamik güncellenir)
TRADING_PAIRS = [
    "BTCUSDT", "ETHUSDT", "USDCUSDT", "SOLUSDT", "ZECUSDT",
    "FDUSDUSDT", "XRPUSDT", "BNBUSDT", "SUIUSDT", "DOGEUSDT",
    "LINKUSDT", "ASTERUSDT", "AVAXUSDT", "ADAUSDT", "ENAUSDT",
    "BCHUSDT", "TRXUSDT", "PEPEUSDT", "SAPIENUSDT", "XPLUSDT",
    "BFUSDUSDT", "LTCUSDT", "GIGGLEUSDT", "TAOUSDT", "NEARUSDT",
    "ATUSDT", "PAXGUSDT", "HBARUSDT", "UNIUSDT", "VIRTUALUSDT",
    "PUMPUSDT", "SHIBUSDT", "PENGUUSDT", "DASHUSDT", "AAVEUSDT",
    "EURUSDT", "ICPUSDT", "WLDUSDT", "FETUSDT", "USDEUSDT",
    "SXPUSDT", "TURBOUSDT", "XLMUSDT", "DOTUSDT", "WIFUSDT",
    "MMTUSDT", "CRVUSDT", "ZENUSDT", "2ZUSDT", "XUSDUSDT",
    "LAYERUSDT", "ARBUSDT", "FILUSDT", "ALLOUSDT", "WLFIUSDT",
    "BATUSDT", "TRUMPUSDT", "TONUSDT", "APTUSDT", "STRKUSDT",
    "PARTIUSDT", "HEIUSDT", "TIAUSDT", "CAKEUSDT", "BONKUSDT",
    "KITEUSDT", "REDUSDT", "EIGENUSDT", "POLUSDT", "ZKUSDT",
    "TNSRUSDT", "SEIUSDT", "ETHFIUSDT", "VOXELUSDT", "ONDOUSDT",
    "WBTCUSDT", "FFUSDT", "OPUSDT", "FLOKIUSDT", "NEIROUSDT",
    "SAHARAUSDT", "TRBUSDT", "LDOUSDT", "ARUSDT", "ETCUSDT",
    "USDPUSDT", "LINEAUSDT", "INJUSDT", "WCTUSDT", "CHESSUSDT",
    "SYRUPUSDT", "LSKUSDT", "ZROUSDT", "JSTUSDT", "PENDLEUSDT",
    "METUSDT", "BARDUSDT", "BERAUSDT", "EDENUSDT", "RENDERUSDT"
]

# 10 İNDİKATÖR AYARLARI - UNIVERSAL SET (BTC + ETH Optimal)
# 3 yıllık backtest sonuçlarına göre %51 accuracy
INDICATORS_CONFIG = [
    {"name": "trend_adx_neg", "threshold": 21.362404102165037, "direction": "UP"},
    {"name": "trend_vortex_ind_neg", "threshold": 1.000056583514445, "direction": "UP"},
    {"name": "volatility_ui", "threshold": 0.4241730142870761, "direction": "UP"},
    {"name": "trend_aroon_down", "threshold": 40.0, "direction": "UP"},
    {"name": "trend_dpo", "threshold": -0.31850000000031287, "direction": "UP"},
    {"name": "volatility_kcw", "threshold": 0.6170914204953815, "direction": "UP"},
    {"name": "volatility_bbw", "threshold": 1.1455399582149561, "direction": "UP"},
    {"name": "trend_mass_index", "threshold": 24.80447336091941, "direction": "UP"},
    {"name": "volatility_dcw", "threshold": 1.4452255358757635, "direction": "UP"},
    {"name": "volatility_atr", "threshold": 76.85628394025728, "direction": "UP"}
]

# Binance API (demo için simulasyon)
BASE_URL = "https://api.binance.com"

# ============================================================================
# GLOBAL STATE
# ============================================================================

state = {
    'running': False,
    'connected': False,
    'balance': DEMO_BALANCE,
    'total_pnl': 0.0,
    'total_commission': 0.0,  # Toplam ödenen komisyon
    'open_positions': [],
    'trade_history': [],
    'logs': [],
    'winning_trades': 0,
    'losing_trades': 0,
    'demo_mode': DEMO_MODE,
    'scan_count': 0,
    'signals_detected': 0,
    # ADAPTİF ÖĞRENME SİSTEMİ
    'current_min_votes': MIN_INDICATOR_VOTES,  # Dinamik indikatör eşiği
    'coin_blacklist': {},  # {symbol: blacklist_until_timestamp}
    'coin_performance': {},  # {symbol: {'wins': 0, 'losses': 0, 'total_pnl': 0}}
    'last_analysis_trade_count': 0,  # Son analiz yapılan trade sayısı
    'learning_active': ADAPTIVE_LEARNING,
    'optimal_threshold_found': False,  # %50'ye ulaşıldı mı?
    'threshold_history': [],  # Threshold değişim geçmişi
    'last_trade_time': time.time(),  # Son işlem zamanı
    'long_positions': 0,  # Açık LONG pozisyon sayısı
    'short_positions': 0,  # Açık SHORT pozisyon sayısı
    'coin_cooldown': {},  # {symbol: cooldown_until_timestamp} - 2 saat bekleme
    # HİBRİT DİNAMİK LİSTE SİSTEMİ
    'active_coin_list': TRADING_PAIRS.copy(),  # Dinamik coin listesi
    'coin_volume_history': {},  # {symbol: [volume1, volume2, ...]} - Pump algılama için
    'last_full_scan_time': 0,  # Son tam market taraması zamanı
    'pump_detected_coins': [],  # Pump algılanan coinler (öncelik için)
    'dynamic_list_stats': {  # İstatistikler
        'total_scans': 0,
        'coins_added': 0,
        'coins_removed': 0,
        'pumps_detected': 0
    },
    # PİYASA TRENDİ SİSTEMİ
    'market_trend': 'SIDEWAYS',  # BULLISH / BEARISH / SIDEWAYS
    'market_trend_strength': 0.0,  # -100 ile +100 arası (- = düşüş, + = yükseliş)
    'last_trend_check': 0,  # Son trend kontrolü zamanı
    'trend_sma_fast': 0.0,  # Hızlı SMA (20 periyot)
    'trend_sma_slow': 0.0,  # Yavaş SMA (50 periyot)
    # PRE-CANDLE ANALYSIS PERFORMANCE METRICS
    'pre_candle_metrics': {
        'total_signals': 0,
        'correct_predictions': 0,
        'wrong_predictions': 0,
        'conflicts_with_indicators': 0,
        'synergy_with_indicators': 0,
        'accuracy': 0.0,
        'last_signals': []  # Son 20 sinyal
    },
    'hybrid_metrics': {
        'version_1_trades': 0,  # Serial Filter
        'version_2_trades': 0,  # Confidence Score
        'version_3_trades': 0,  # Priority System
        'version_1_wins': 0,
        'version_2_wins': 0,
        'version_3_wins': 0,
        'best_version': None
    }
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def add_log(message, level="INFO"):
    """Log mesajı ekle"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {
        'time': timestamp,
        'level': level,
        'message': message
    }
    state['logs'].append(log_entry)
    if len(state['logs']) > 100:
        state['logs'].pop(0)

    # Console'a da yazdır
    icon = "✅" if level == "SUCCESS" else "❌" if level == "ERROR" else "📊" if level == "TRADE" else "ℹ️"
    print(f"{icon} [{timestamp}] {message}")

def get_price(symbol):
    """Binance'den anlık fiyat çek (demo mode için GERÇEK fiyat + küçük simülasyon)"""
    try:
        # HER ZAMAN GERÇEK FİYATI ÇEK (demo mode bile olsa)
        response = requests.get(f"{BASE_URL}/api/v3/ticker/price?symbol={symbol}", timeout=2)
        if response.status_code == 200:
            real_price = float(response.json()['price'])

            if DEMO_MODE:
                # Gerçek fiyat üzerine KÜÇÜK rastgele hareket ekle (-0.05% ile +0.05%)
                # Bu daha gerçekçi ve stop loss'u aşmaz
                movement = np.random.uniform(-0.0005, 0.0005)
                return real_price * (1 + movement)
            else:
                return real_price
    except:
        pass

    return None

def get_24h_ticker(symbol):
    """24h ticker verisi al (volume kontrolü için)"""
    try:
        url = f"{BASE_URL}/api/v3/ticker/24hr"
        params = {'symbol': symbol}
        response = requests.get(url, params=params, timeout=5)

        if response.status_code == 200:
            data = response.json()
            return {
                'volume_24h': float(data['quoteVolume']),  # USDT cinsinden hacim
                'price_change_percent': float(data['priceChangePercent'])
            }
    except Exception as e:
        pass

    return None

def check_volatility(symbol):
    """
    VOLATİLİTE FİLTRESİ - Çok durgun veya çok çılgın coinleri filtrele

    Returns:
        True: Volatilite uygun, işlem yapılabilir
        False: Volatilite uygun değil, işlem yapma
    """
    if not VOLATILITY_FILTER_ENABLED:
        return True  # Filtre kapalı, tüm coinler uygun

    ticker_data = get_24h_ticker(symbol)
    if ticker_data is None:
        return False  # Veri alınamadı, güvenli tarafta dur

    price_change_24h = abs(ticker_data['price_change_percent'])

    # Çok durgun coin mu? (örn: %0.5'in altında hareket)
    if price_change_24h < MIN_VOLATILITY_24H:
        add_log(f"⏸️ {symbol} çok durgun (24h: {price_change_24h:.2f}%) - Atlandı", "FILTER")
        return False

    # Çok çılgın coin mu? (örn: %15'in üstünde hareket)
    if price_change_24h > MAX_VOLATILITY_24H:
        add_log(f"🔥 {symbol} çok volatil (24h: {price_change_24h:.2f}%) - Atlandı", "FILTER")
        return False

    return True

def update_market_trend(state):
    """
    PİYASA TRENDİ ALGILAMA SİSTEMİ

    BTCUSDT'yi referans alarak genel piyasa trendini belirler:
    - BULLISH (Yükseliş): Hızlı SMA > Yavaş SMA → LONG işlemleri 2x ağırlıklı
    - BEARISH (Düşüş): Hızlı SMA < Yavaş SMA → SHORT işlemleri 2x ağırlıklı
    - SIDEWAYS (Yatay): SMA'lar yakın → Normal işlem

    Returns:
        bool: Güncelleme yapıldı mı?
    """
    if not MARKET_TREND_ENABLED:
        return False

    current_time = time.time()

    # Her 60 saniyede bir kontrol et
    if current_time - state['last_trend_check'] < MARKET_TREND_CHECK_INTERVAL:
        return False

    try:
        # BTC kline verilerini al (50 mum, 15 dakikalık)
        url = f"{BASE_URL}/api/v3/klines"
        params = {
            'symbol': MARKET_TREND_REFERENCE_COIN,
            'interval': '15m',
            'limit': MARKET_TREND_PERIOD
        }

        response = requests.get(url, params=params, timeout=5)
        if response.status_code != 200:
            return False

        klines = response.json()

        # Kapanış fiyatlarını al
        close_prices = [float(k[4]) for k in klines]

        # SMA hesapla
        sma_fast = sum(close_prices[-20:]) / 20  # Hızlı: Son 20 mum (5 saat)
        sma_slow = sum(close_prices) / len(close_prices)  # Yavaş: Tüm 50 mum (12.5 saat)

        # Trend gücü: Fast ve Slow arasındaki fark (yüzde olarak)
        strength = ((sma_fast - sma_slow) / sma_slow) * 100

        # Trend belirle
        if strength > 0.3:  # %0.3'ten fazla yukarıda → BULLISH
            trend = 'BULLISH'
            emoji = '🟢'
        elif strength < -0.3:  # %0.3'ten fazla aşağıda → BEARISH
            trend = 'BEARISH'
            emoji = '🔴'
        else:  # Yakın → SIDEWAYS
            trend = 'SIDEWAYS'
            emoji = '🟡'

        # Trend değişti mi?
        old_trend = state['market_trend']
        trend_changed = old_trend != trend

        # State'i güncelle
        state['market_trend'] = trend
        state['market_trend_strength'] = strength
        state['last_trend_check'] = current_time
        state['trend_sma_fast'] = sma_fast
        state['trend_sma_slow'] = sma_slow

        # Trend değişikliğini logla
        if trend_changed:
            add_log(f"{emoji} PİYASA TRENDİ DEĞİŞTİ: {old_trend} → {trend} (Güç: {strength:+.2f}%)", "TREND")
            if trend == 'BULLISH':
                add_log(f"   📈 LONG işlemler 2x ağırlıklı, SHORT işlemler azaltıldı", "TREND")
            elif trend == 'BEARISH':
                add_log(f"   📉 SHORT işlemler 2x ağırlıklı, LONG işlemler azaltıldı", "TREND")
            else:
                add_log(f"   ➡️ Yatay piyasa, normal işlem devam ediyor", "TREND")

        return True

    except Exception as e:
        add_log(f"⚠️ Trend güncelleme hatası: {e}", "ERROR")
        return False

def get_volume_direction(symbol):
    """
    HACİM YÖNÜ ANALİZİ - Trade History
    Son 5 dakikadaki gerçek alım/satım işlemlerine bakarak hacim yönünü tespit eder

    Returns:
        'BUY_HEAVY': Alım ağırlıklı (LONG aç)
        'SELL_HEAVY': Satım ağırlıklı (SHORT aç)
        'NEUTRAL': Net değil
    """
    try:
        url = f"{BASE_URL}/api/v3/trades"
        params = {'symbol': symbol, 'limit': 500}  # Son 500 işlem

        response = requests.get(url, params=params, timeout=5)
        if response.status_code != 200:
            return 'NEUTRAL'

        trades = response.json()

        # Son 5 dakikadaki işlemleri filtrele
        current_time = int(time.time() * 1000)
        five_min_ago = current_time - (5 * 60 * 1000)

        buy_volume = 0
        sell_volume = 0

        for trade in trades:
            if trade['time'] < five_min_ago:
                continue

            qty = float(trade['qty'])
            price = float(trade['price'])
            volume = qty * price  # USDT cinsinden hacim

            # isBuyerMaker: False ise AL (market buy), True ise SAT (market sell)
            if trade['isBuyerMaker'] == False:  # Alıcı market order kullandı → AL baskısı
                buy_volume += volume
            else:  # Satıcı market order kullandı → SAT baskısı
                sell_volume += volume

        total_volume = buy_volume + sell_volume

        if total_volume == 0:
            return 'NEUTRAL'

        buy_ratio = buy_volume / total_volume

        # %60+ AL baskısı → LONG aç
        if buy_ratio >= 0.60:
            return 'BUY_HEAVY'
        # %40- AL baskısı (%60+ SAT) → SHORT aç
        elif buy_ratio <= 0.40:
            return 'SELL_HEAVY'
        else:
            return 'NEUTRAL'

    except Exception as e:
        return 'NEUTRAL'

def get_orderbook_pressure(symbol):
    """
    ORDER BOOK BASKISI ANALİZİ
    Mevcut emir defterindeki BID/ASK hacmine bakarak alıcı/satıcı baskısını ölçer

    Returns:
        'BUY_PRESSURE': Güçlü alıcı baskısı (LONG)
        'SELL_PRESSURE': Güçlü satıcı baskısı (SHORT)
        'NEUTRAL': Net değil
    """
    try:
        url = f"{BASE_URL}/api/v3/depth"
        params = {'symbol': symbol, 'limit': 100}  # En iyi 100 seviye

        response = requests.get(url, params=params, timeout=5)
        if response.status_code != 200:
            return 'NEUTRAL'

        data = response.json()

        # BID (alım emirleri) hacmi
        bid_volume = sum([float(price) * float(qty) for price, qty in data['bids']])

        # ASK (satım emirleri) hacmi
        ask_volume = sum([float(price) * float(qty) for price, qty in data['asks']])

        total_volume = bid_volume + ask_volume

        if total_volume == 0:
            return 'NEUTRAL'

        bid_ratio = bid_volume / total_volume

        # %55+ BID → Güçlü alıcı baskısı → LONG
        if bid_ratio >= 0.55:
            return 'BUY_PRESSURE'
        # %45- BID → Güçlü satıcı baskısı → SHORT
        elif bid_ratio <= 0.45:
            return 'SELL_PRESSURE'
        else:
            return 'NEUTRAL'

    except Exception as e:
        return 'NEUTRAL'

def detect_instant_momentum(symbol='BTCUSDT'):
    """
    ANİ MOMENTUM TESPİTİ - Ultra Hızlı Trend Yakalama

    Son 5-10-15 mumda %0.5+ hareket varsa güçlü sinyal döndürür.
    Bu sayede piyasanın ani dönüşlerini ANINDA yakalayıp:
    - Düşüş başlayınca hemen SHORT'a geç
    - Yükseliş başlayınca hemen LONG'a geç

    Returns:
        'INSTANT_BUY': Son 5-15 dakikada %0.5+ yükseliş → SHORT REDDET, LONG 5x
        'INSTANT_SELL': Son 5-15 dakikada %0.5+ düşüş → LONG REDDET, SHORT 5x
        'NEUTRAL': Belirgin hareket yok
    """
    try:
        # Son 15 mum al (1 dakikalık mumlar = 15 dakika)
        url = f"{BASE_URL}/api/v3/klines"
        params = {
            'symbol': symbol,
            'interval': '1m',  # 1 dakikalık mumlar (en hızlı)
            'limit': 15
        }

        response = requests.get(url, params=params, timeout=3)
        if response.status_code != 200:
            return 'NEUTRAL'

        klines = response.json()

        if len(klines) < 15:
            return 'NEUTRAL'

        # Kapanış fiyatlarını al
        closes = [float(k[4]) for k in klines]

        # 3 farklı periyotta momentum hesapla
        price_now = closes[-1]
        price_5min = closes[-5]   # 5 dakika önce
        price_10min = closes[-10]  # 10 dakika önce
        price_15min = closes[0]    # 15 dakika önce

        # Değişim yüzdeleri
        change_5min = ((price_now - price_5min) / price_5min) * 100
        change_10min = ((price_now - price_10min) / price_10min) * 100
        change_15min = ((price_now - price_15min) / price_15min) * 100

        # GÜÇLÜ YUKARI MOMENTUM (en az 2 periyotta %0.5+ yükseliş)
        bullish_signals = sum([
            change_5min >= 0.5,
            change_10min >= 0.5,
            change_15min >= 0.5
        ])

        # GÜÇLÜ AŞAĞI MOMENTUM (en az 2 periyotta %0.5+ düşüş)
        bearish_signals = sum([
            change_5min <= -0.5,
            change_10min <= -0.5,
            change_15min <= -0.5
        ])

        if bullish_signals >= 2:
            # ANLIK YUKARI MOMENTUM - SHORT'LARI REDDET!
            add_log(f"🚀 ANİ YUKARI MOMENTUM: {symbol} +%{change_5min:.2f} (5dk), +%{change_10min:.2f} (10dk)", "MOMENTUM")
            return 'INSTANT_BUY'
        elif bearish_signals >= 2:
            # ANLIK AŞAĞI MOMENTUM - LONG'LARI REDDET!
            add_log(f"📉 ANİ AŞAĞI MOMENTUM: {symbol} -%{abs(change_5min):.2f} (5dk), -%{abs(change_10min):.2f} (10dk)", "MOMENTUM")
            return 'INSTANT_SELL'
        else:
            return 'NEUTRAL'

    except Exception as e:
        return 'NEUTRAL'

def analyze_pre_candle(symbol, timeframe='15m'):
    """
    MUM KAPANIŞINA YAKIN NEXT CANDLE TAHMİNİ

    5 Faktör Analizi:
    1. Son 3 mumun trend yönü
    2. Hacim akışı (son 5 dakika trade history)
    3. Order book baskısı (BID vs ASK)
    4. Momentum gücü (ATR ve fiyat hareketi)
    5. Whale activity (büyük işlemler)

    Returns:
        'STRONG_UP': %75+ yukarı ihtimali (5/5 veya 4/5 faktör)
        'STRONG_DOWN': %75+ aşağı ihtimali (5/5 veya 4/5 faktör)
        'WEAK_UP': Zayıf yukarı (3/5 faktör)
        'WEAK_DOWN': Zayıf aşağı (3/5 faktör)
        'NEUTRAL': Belirsiz (2/5 veya daha az)
    """
    try:
        factors = {
            'trend': 0,      # -1 (DOWN) veya +1 (UP)
            'volume': 0,     # -1 (SELL) veya +1 (BUY)
            'orderbook': 0,  # -1 (SELL) veya +1 (BUY)
            'momentum': 0,   # -1 (DOWN) veya +1 (UP)
            'whale': 0       # -1 (SELL) veya +1 (BUY)
        }

        # FAKTÖR 1: TREND (Son 3 mum)
        df = get_klines(symbol, interval=timeframe, limit=5)
        if df is not None and len(df) >= 3:
            last_3_closes = df['Close'].tail(3).tolist()
            if last_3_closes[2] > last_3_closes[1] > last_3_closes[0]:
                factors['trend'] = 1  # Yükseliş trendi
            elif last_3_closes[2] < last_3_closes[1] < last_3_closes[0]:
                factors['trend'] = -1  # Düşüş trendi

        # FAKTÖR 2: VOLUME FLOW (Trade History)
        volume_dir = get_volume_direction(symbol)
        if volume_dir == 'BUY_HEAVY':
            factors['volume'] = 1
        elif volume_dir == 'SELL_HEAVY':
            factors['volume'] = -1

        # FAKTÖR 3: ORDER BOOK BASKISI
        orderbook_pressure = get_orderbook_pressure(symbol)
        if orderbook_pressure == 'BUY_PRESSURE':
            factors['orderbook'] = 1
        elif orderbook_pressure == 'SELL_PRESSURE':
            factors['orderbook'] = -1

        # FAKTÖR 4: MOMENTUM (Son 1 saat)
        if df is not None and len(df) >= 4:
            last_row = calculate_indicators(df)
            if last_row is not None:
                atr = last_row['volatility_atr']
                current_price = last_row['Close']

                # Son 4 mum fiyat hareketi
                price_4_ago = df['Close'].iloc[-4]
                price_change = (current_price - price_4_ago) / price_4_ago

                # Güçlü momentum: ATR'nin %50'sinden fazla hareket
                if price_change > 0.005:  # +%0.5
                    factors['momentum'] = 1
                elif price_change < -0.005:  # -%0.5
                    factors['momentum'] = -1

        # FAKTÖR 5: WHALE ACTIVITY (Son 100 işlem)
        try:
            url = f"{BASE_URL}/api/v3/trades"
            params = {'symbol': symbol, 'limit': 100}
            response = requests.get(url, params=params, timeout=3)

            if response.status_code == 200:
                trades = response.json()

                # Büyük işlemleri filtrele (avg'nin 3x üstü)
                volumes = [float(t['qty']) * float(t['price']) for t in trades]
                avg_volume = sum(volumes) / len(volumes) if volumes else 0

                large_buys = sum(1 for t in trades if not t['isBuyerMaker'] and float(t['qty']) * float(t['price']) > avg_volume * 3)
                large_sells = sum(1 for t in trades if t['isBuyerMaker'] and float(t['qty']) * float(t['price']) > avg_volume * 3)

                if large_buys > large_sells * 1.5:
                    factors['whale'] = 1
                elif large_sells > large_buys * 1.5:
                    factors['whale'] = -1
        except:
            pass

        # SKOR HESAPLAMA
        total_score = sum(factors.values())
        positive_factors = sum(1 for v in factors.values() if v == 1)
        negative_factors = sum(1 for v in factors.values() if v == -1)

        # Sinyal belirleme
        if total_score >= 4 or positive_factors >= 4:
            signal = 'STRONG_UP'
        elif total_score >= 3:
            signal = 'WEAK_UP'
        elif total_score <= -4 or negative_factors >= 4:
            signal = 'STRONG_DOWN'
        elif total_score <= -3:
            signal = 'WEAK_DOWN'
        else:
            signal = 'NEUTRAL'

        # Metrik kaydet
        state['pre_candle_metrics']['total_signals'] += 1
        state['pre_candle_metrics']['last_signals'].append({
            'symbol': symbol,
            'signal': signal,
            'score': total_score,
            'factors': factors.copy(),
            'time': datetime.now().strftime("%H:%M:%S")
        })

        # Son 20 sinyali tut
        if len(state['pre_candle_metrics']['last_signals']) > 20:
            state['pre_candle_metrics']['last_signals'].pop(0)

        if signal in ['STRONG_UP', 'STRONG_DOWN']:
            add_log(f"🎯 PRE-CANDLE: {symbol} → {signal} (Skor: {total_score}/5, Faktörler: {factors})", "PRECANDLE")

        return signal, factors, total_score

    except Exception as e:
        add_log(f"⚠️ Pre-candle analiz hatası: {e}", "ERROR")
        return 'NEUTRAL', {}, 0

def get_market_trend():
    """
    PİYASA YÖNÜ ANALİZİ (BTC bazlı)
    Bitcoin'in son 1 saatlik hareketine bakarak genel market trendini belirler

    Returns:
        'STRONG_BULL': Güçlü yükseliş (+%1.5+) → Sadece LONG
        'STRONG_BEAR': Güçlü düşüş (-%1.5+) → Sadece SHORT
        'NEUTRAL': Normal hareket → Her ikisi de OK
    """
    try:
        # BTC'nin son 1 saatlik (60dk) mum verilerini al
        url = f"{BASE_URL}/api/v3/klines"
        params = {
            'symbol': 'BTCUSDT',
            'interval': '1h',  # 1 saatlik mumlar
            'limit': 2  # Son 2 mum (şu anki + önceki)
        }

        response = requests.get(url, params=params, timeout=5)
        if response.status_code != 200:
            return 'NEUTRAL'

        candles = response.json()

        if len(candles) < 2:
            return 'NEUTRAL'

        # Önceki mumun kapanış fiyatı
        prev_close = float(candles[-2][4])

        # Şu anki mumun anlık fiyatı
        current_close = float(candles[-1][4])

        # Değişim yüzdesi
        change_percent = ((current_close - prev_close) / prev_close) * 100

        # Sert hareketleri tespit et
        if change_percent >= 1.5:
            return 'STRONG_BULL'  # +%1.5+ → Güçlü yükseliş
        elif change_percent <= -1.5:
            return 'STRONG_BEAR'  # -%1.5+ → Güçlü düşüş
        else:
            return 'NEUTRAL'  # Normal hareket

    except Exception as e:
        return 'NEUTRAL'

def should_trade_with_volume_confirmation(symbol, indicator_signal):
    """
    İndikatör sinyalini hacim yönüyle VE piyasa trendiyle doğrula

    1. Trade History + Order Book kontrolü (biri uyarsa yeter)
    2. BTC bazlı piyasa trend kontrolü (sert hareketlerde ters işlem yapma)

    Args:
        symbol: Coin sembolü
        indicator_signal: 'BUY' veya 'SELL'

    Returns:
        tuple: (bool: işlem açılsın mı?, str: sebep)
    """
    # ========================================================================
    # 1. HACİM YÖNÜ KONTROLÜ
    # ========================================================================
    volume_direction = get_volume_direction(symbol)
    orderbook_pressure = get_orderbook_pressure(symbol)

    volume_ok = False
    volume_reason = ""

    if indicator_signal == 'BUY':
        # Hacim AL yönünde mi veya NEUTRAL mı?
        if volume_direction == 'BUY_HEAVY':
            volume_ok = True
            volume_reason = "Trade History: AL baskisi"
        elif orderbook_pressure == 'BUY_PRESSURE':
            volume_ok = True
            volume_reason = "Order Book: AL baskisi"
        elif volume_direction == 'NEUTRAL' or orderbook_pressure == 'NEUTRAL':
            volume_ok = True
            volume_reason = "Hacim notr - islem izin verildi"
        else:
            # HER IKI DE SAT baskısı = ters yönde, iptal et
            if volume_direction == 'SELL_HEAVY' and orderbook_pressure == 'SELL_PRESSURE':
                return False, f"Hacim ters yonde (TH:{volume_direction}, OB:{orderbook_pressure})"
            else:
                # Sadece 1 tanesi ters = izin ver (daha esnek!)
                volume_ok = True
                volume_reason = "Hacim karisik - islem izin verildi"

    elif indicator_signal == 'SELL':
        # Hacim SAT yönünde mi veya NEUTRAL mı?
        if volume_direction == 'SELL_HEAVY':
            volume_ok = True
            volume_reason = "Trade History: SAT baskisi"
        elif orderbook_pressure == 'SELL_PRESSURE':
            volume_ok = True
            volume_reason = "Order Book: SAT baskisi"
        elif volume_direction == 'NEUTRAL' or orderbook_pressure == 'NEUTRAL':
            volume_ok = True
            volume_reason = "Hacim notr - islem izin verildi"
        else:
            # HER IKI DE AL baskısı = ters yönde, iptal et
            if volume_direction == 'BUY_HEAVY' and orderbook_pressure == 'BUY_PRESSURE':
                return False, f"Hacim ters yonde (TH:{volume_direction}, OB:{orderbook_pressure})"
            else:
                # Sadece 1 tanesi ters = izin ver (daha esnek!)
                volume_ok = True
                volume_reason = "Hacim karisik - islem izin verildi"

    # ========================================================================
    # 2. PİYASA TRENDİ KONTROLÜ (BTC) - DAHA ESNEK!
    # ========================================================================
    market_trend = get_market_trend()

    # SADECE STRONG_BEAR'da LONG'u iptal et (SHORT serbest!)
    if market_trend == 'STRONG_BEAR' and indicator_signal == 'BUY':
        return False, f"Piyasa sert dusuyor (BTC), LONG'a girilmez"

    # STRONG_BULL'da SHORT izin ver! (Dip yakalamak için fırsat!)
    # Sadece çok aşırı durumlarda iptal et
    # NOT: Bu satırı kaldırıyoruz - SHORT sinyalleri artık STRONG_BULL'da da açılacak

    # Her iki kontrol de geçti
    return True, f"{volume_reason} + Market: {market_trend}"

def full_market_scan():
    """
    HİBRİT DİNAMİK LİSTE - TAM MARKET TARAMASI
    Tüm Binance USDT çiftlerini tara ve dinamik listeyi güncelle
    """
    if not DYNAMIC_COIN_LIST:
        return  # Dinamik liste kapalıysa tarama yapma

    try:
        add_log("Tam market taramasi basliyor...", "INFO")

        # Tüm 24h ticker verilerini al
        response = requests.get(f"{BASE_URL}/api/v3/ticker/24hr", timeout=10)
        if response.status_code != 200:
            return

        all_tickers = response.json()

        # USDT çiftlerini filtrele
        usdt_pairs = []
        for ticker in all_tickers:
            symbol = ticker['symbol']

            # USDT ile biten mi?
            if not symbol.endswith('USDT'):
                continue

            # Fiat para çiftlerini filtrele (TRY, EUR, GBP, vb.)
            is_fiat = False
            for fiat in EXCLUDED_FIAT_PAIRS:
                if symbol.startswith(fiat):
                    is_fiat = True
                    break

            if is_fiat:
                continue

            # Kaldıraçlı tokenları filtrele (UP, DOWN, BULL, BEAR)
            if (symbol.startswith('UP') or symbol.startswith('DOWN') or
                symbol.startswith('BULL') or symbol.startswith('BEAR')):
                continue

            volume_24h = float(ticker['quoteVolume'])

            # Minimum hacim kontrolü
            if volume_24h >= MIN_24H_VOLUME:
                usdt_pairs.append({
                    'symbol': symbol,
                    'volume': volume_24h
                })

        # Hacme göre sırala
        usdt_pairs.sort(key=lambda x: x['volume'], reverse=True)

        # Pump algılama
        new_pumps = []
        for pair in usdt_pairs:
            symbol = pair['symbol']
            current_volume = pair['volume']

            # Volume geçmişini kontrol et
            if symbol in state['coin_volume_history']:
                history = state['coin_volume_history'][symbol]
                if len(history) >= 3:
                    avg_volume = sum(history[-3:]) / 3

                    # 5x hacim artışı = PUMP!
                    if PUMP_DETECTION_ENABLED and current_volume > avg_volume * PUMP_VOLUME_MULTIPLIER:
                        if symbol not in state['pump_detected_coins']:
                            new_pumps.append(symbol)
                            state['pump_detected_coins'].append(symbol)
                            state['dynamic_list_stats']['pumps_detected'] += 1
                            add_log(f"PUMP ALGILANDI: {symbol} (Hacim: ${current_volume/1_000_000:.1f}M, Onceki ort: ${avg_volume/1_000_000:.1f}M)", "SUCCESS")

            # Volume geçmişini güncelle (son 5 taramayı tut)
            if symbol not in state['coin_volume_history']:
                state['coin_volume_history'][symbol] = []
            state['coin_volume_history'][symbol].append(current_volume)
            if len(state['coin_volume_history'][symbol]) > 5:
                state['coin_volume_history'][symbol].pop(0)

        # Yeni aktif coin listesi oluştur
        new_active_list = []

        # 1. Açık pozisyonu olan coinleri ekle (POZİSYON KORUMA)
        if PROTECT_OPEN_POSITIONS:
            for pos in state['open_positions']:
                if pos['symbol'] not in new_active_list:
                    new_active_list.append(pos['symbol'])

        # 2. Pump algılanan coinleri ekle (ÖNCELİK)
        for symbol in state['pump_detected_coins']:
            if symbol not in new_active_list:
                new_active_list.append(symbol)

        # 3. Diğer yüksek hacimli coinleri ekle
        for pair in usdt_pairs:
            symbol = pair['symbol']
            if symbol not in new_active_list:
                new_active_list.append(symbol)

        # Akıllı limit kontrolü (200+ coin olunca önceliklendirme)
        if SMART_LIMIT_ENABLED and len(new_active_list) > SMART_LIMIT_THRESHOLD:
            # İlk 200'ü al (pump ve pozisyonlar zaten başta)
            original_count = len(new_active_list)
            new_active_list = new_active_list[:SMART_LIMIT_THRESHOLD]
            add_log(f"Akilli limit aktif: {original_count} coindan {SMART_LIMIT_THRESHOLD} tanesi secildi", "INFO")

        # İstatistikleri güncelle
        old_list = set(state['active_coin_list'])
        new_list = set(new_active_list)

        coins_added = len(new_list - old_list)
        coins_removed = len(old_list - new_list)

        state['dynamic_list_stats']['total_scans'] += 1
        state['dynamic_list_stats']['coins_added'] += coins_added
        state['dynamic_list_stats']['coins_removed'] += coins_removed

        # Listeyi güncelle
        state['active_coin_list'] = new_active_list
        state['last_full_scan_time'] = time.time()

        add_log(f"Market taramasi tamamlandi: {len(new_active_list)} coin aktif (+{coins_added} -{coins_removed})", "SUCCESS")

        if new_pumps:
            add_log(f"Yeni pump tespit edildi: {', '.join(new_pumps)}", "SUCCESS")

    except Exception as e:
        add_log(f"Market taramasi hatasi: {str(e)}", "ERROR")

def get_klines(symbol, interval='15m', limit=100):
    """Binance'den historical kline data çek"""
    try:
        url = f"{BASE_URL}/api/v3/klines"
        params = {'symbol': symbol, 'interval': interval, 'limit': limit}
        response = requests.get(url, params=params)

        if response.status_code == 200:
            klines = response.json()
            df = pd.DataFrame(klines, columns=[
                'open_time', 'Open', 'High', 'Low', 'Close', 'Volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])

            # Convert to numeric
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            return df

    except Exception as e:
        add_log(f"❌ Kline verisi alınamadı {symbol}: {e}", "ERROR")

    return None

def calculate_indicators(df):
    """10 indikatörü hesapla"""
    if df is None or len(df) < 50:
        return None

    try:
        from ta.volatility import BollingerBands, AverageTrueRange, KeltnerChannel, DonchianChannel, UlcerIndex
        from ta.trend import ADXIndicator, VortexIndicator, AroonIndicator, DPOIndicator, MassIndex

        # Volatility indicators (zaten var olanlar)
        bb = BollingerBands(df['Close'])
        df['volatility_kcw'] = KeltnerChannel(df['High'], df['Low'], df['Close']).keltner_channel_wband()
        df['volatility_atr'] = AverageTrueRange(df['High'], df['Low'], df['Close']).average_true_range()
        df['volatility_bbw'] = bb.bollinger_wband()
        df['volatility_dcw'] = DonchianChannel(df['High'], df['Low'], df['Close']).donchian_channel_wband()
        df['volatility_ui'] = UlcerIndex(df['Close']).ulcer_index()

        # Trend indicators (yeni optimal setler)
        adx_ind = ADXIndicator(df['High'], df['Low'], df['Close'])
        df['trend_adx_neg'] = adx_ind.adx_neg()

        vortex = VortexIndicator(df['High'], df['Low'], df['Close'])
        df['trend_vortex_ind_neg'] = vortex.vortex_indicator_neg()

        aroon = AroonIndicator(df['Close'], df['Close'])  # high, low parametreleri (close kullan)
        df['trend_aroon_down'] = aroon.aroon_down()

        df['trend_dpo'] = DPOIndicator(df['Close']).dpo()
        df['trend_mass_index'] = MassIndex(df['High'], df['Low']).mass_index()

        # Son satırı al
        return df.iloc[-1]

    except Exception as e:
        add_log(f"❌ İndikatör hesaplama hatası: {e}", "ERROR")
        return None

def check_10_indicator_signals(symbol):
    """10 indikatörü kontrol et, 3/10 kuralı uygula"""
    # KARA LİSTE KONTROLÜ (Adaptif öğrenme)
    if state['learning_active']:
        blacklist_result = check_coin_blacklist(state, symbol, {
            'COIN_BLACKLIST_HOURS': COIN_BLACKLIST_HOURS
        })
        if blacklist_result:
            if isinstance(blacklist_result, dict) and blacklist_result.get('blacklisted'):
                add_log(f"⛔ {symbol} kara listede: {blacklist_result['reason']} (Kalkış: {blacklist_result['until']})", "INFO")
                return None, 0, 0
            elif blacklist_result is True:
                return None, 0, 0

    # Kline verisi çek
    df = get_klines(symbol, interval='15m', limit=100)
    if df is None:
        return None, 0, 0

    # İndikatörleri hesapla
    last_row = calculate_indicators(df)
    if last_row is None:
        return None, 0, 0

    # ========================================================================
    # FİLTRE 1: VOLUME (Hacim) FİLTRESİ
    # ========================================================================
    ticker_data = get_24h_ticker(symbol)
    if ticker_data:
        volume_24h = ticker_data['volume_24h']
        if volume_24h < MIN_24H_VOLUME:
            # Düşük hacim, sinyal verme
            return None, 0, 0

    # ========================================================================
    # FİLTRE 2: VOLATILITY (Oynaklık) FİLTRESİ
    # ========================================================================
    current_price = last_row['Close']
    atr_value = last_row['volatility_atr']
    min_atr = current_price * MIN_VOLATILITY_PERCENT  # Fiyatın %0.3'ü

    if atr_value < min_atr:
        # Çok düşük volatility, coin hareket etmiyor
        return None, 0, 0

    buy_votes = 0
    sell_votes = 0

    # Her indikatörü kontrol et
    for ind in INDICATORS_CONFIG:
        name = ind['name']
        threshold = ind['threshold']
        direction = ind['direction']

        if name not in last_row or pd.isna(last_row[name]):
            continue

        value = last_row[name]

        # AL sinyali kontrolü
        if direction == 'UP':
            if value > threshold:
                buy_votes += 1
            # SAT sinyali: düşük değerler
            if value < (threshold * INDICATOR_THRESHOLD_MULTIPLIER):
                sell_votes += 1
        else:  # DOWN
            if value < threshold:
                buy_votes += 1
            # SAT sinyali: yüksek değerler
            if value > abs(threshold * INDICATOR_THRESHOLD_MULTIPLIER):
                sell_votes += 1

    # Dinamik threshold: Adaptif öğrenme aktifse current_min_votes kullan
    min_votes = state['current_min_votes'] if state['learning_active'] else MIN_INDICATOR_VOTES

    # N/10 kuralı: N veya daha fazla oy varsa sinyal ver
    signal = None
    if buy_votes >= min_votes:
        signal = 'BUY'
        state['signals_detected'] += 1
    elif sell_votes >= min_votes:
        signal = 'SELL'
        state['signals_detected'] += 1

    # ========================================================================
    # FİLTRE 3: MOMENTUM (Fiyat Yönü) KONTROLÜ
    # ========================================================================
    if MOMENTUM_CHECK_ENABLED and signal is not None:
        # Son 4 mum (1 saat) fiyat hareketi
        if len(df) >= 4:
            price_4_candles_ago = df['Close'].iloc[-4]
            current_price = df['Close'].iloc[-1]
            price_momentum = (current_price - price_4_candles_ago) / price_4_candles_ago

            # BUY sinyali ama fiyat düşüyor → İPTAL
            if signal == 'BUY' and price_momentum < -MOMENTUM_THRESHOLD_PERCENT:
                return None, buy_votes, sell_votes

            # SELL sinyali ama fiyat yükseliyor → İPTAL
            if signal == 'SELL' and price_momentum > MOMENTUM_THRESHOLD_PERCENT:
                return None, buy_votes, sell_votes

    # ========================================================================
    # FİLTRE 4: INSTANT MOMENTUM (Ani Hareket) KONTROLÜ - ULTRA AGRESİF
    # ========================================================================
    if signal is not None:
        instant_momentum = detect_instant_momentum('BTCUSDT')

        # ANİ YUKARI MOMENTUM → SHORT'LARI REDDET, LONG'A 5x AĞIRLIK
        if instant_momentum == 'INSTANT_BUY':
            if signal == 'SELL':
                add_log(f"⛔ {symbol} SHORT sinyali İPTAL: Piyasa ANİ YUKARI momentum'da!", "FILTER")
                return None, buy_votes, sell_votes
            elif signal == 'BUY':
                # LONG sinyali varken yukarı momentum → SÜPERGÜÇLENDİR!
                buy_votes = min(10, int(buy_votes * 1.5))  # Oy sayısını artır (max 10)
                add_log(f"🚀 {symbol} LONG sinyali GÜÇLENDİRİLDİ: Piyasa momentum'u lehimizde! (Oy: {buy_votes})", "BOOST")

        # ANİ AŞAĞI MOMENTUM → LONG'LARI REDDET, SHORT'A 5x AĞIRLIK
        elif instant_momentum == 'INSTANT_SELL':
            if signal == 'BUY':
                add_log(f"⛔ {symbol} LONG sinyali İPTAL: Piyasa ANİ AŞAĞI momentum'da!", "FILTER")
                return None, buy_votes, sell_votes
            elif signal == 'SELL':
                # SHORT sinyali varken aşağı momentum → SÜPERGÜÇLENDİR!
                sell_votes = min(10, int(sell_votes * 1.5))  # Oy sayısını artır (max 10)
                add_log(f"📉 {symbol} SHORT sinyali GÜÇLENDİRİLDİ: Piyasa momentum'u lehimizde! (Oy: {sell_votes})", "BOOST")

    # ========================================================================
    # FİLTRE 5: PRE-CANDLE ANALYSIS - HYBRID DECISION SYSTEM
    # ========================================================================
    if signal is not None:
        pre_signal, pre_factors, pre_score = analyze_pre_candle(symbol)

        # Metrik kaydetme
        if pre_signal != 'NEUTRAL':
            # Çakışma kontrolü (SADECE STRONG sinyaller iptal edilir)
            if (pre_signal == 'STRONG_UP' and signal == 'SELL') or \
               (pre_signal == 'STRONG_DOWN' and signal == 'BUY'):
                state['pre_candle_metrics']['conflicts_with_indicators'] += 1
                add_log(f"⚠️ {symbol} PRE-CANDLE GÜÇLÜ ÇAKIŞMA: Pre={pre_signal}, Ind={signal} → İşlem İPTAL", "CONFLICT")
                return None, buy_votes, sell_votes
            # Sinerji
            elif (pre_signal in ['STRONG_UP', 'WEAK_UP'] and signal == 'BUY') or \
                 (pre_signal in ['STRONG_DOWN', 'WEAK_DOWN'] and signal == 'SELL'):
                state['pre_candle_metrics']['synergy_with_indicators'] += 1

        # VERSION 1: SERIAL FILTER (Sadece ikisi de uyumlu olursa aç)
        version_1_decision = None
        if pre_signal == 'STRONG_UP' and signal == 'BUY':
            version_1_decision = 'BUY'
            buy_votes = min(10, int(buy_votes * 1.3))  # 30% boost
        elif pre_signal == 'STRONG_DOWN' and signal == 'SELL':
            version_1_decision = 'SELL'
            sell_votes = min(10, int(sell_votes * 1.3))

        # VERSION 2: CONFIDENCE SCORE (Birleşik skor)
        confidence = (buy_votes / 10.0) * 0.5  # İndikatör: 50%
        if pre_signal in ['STRONG_UP', 'WEAK_UP']:
            confidence += (abs(pre_score) / 5.0) * 0.5  # Pre-candle: 50%
        version_2_decision = 'BUY' if confidence >= 0.70 else None

        if signal == 'SELL':
            confidence = (sell_votes / 10.0) * 0.5
            if pre_signal in ['STRONG_DOWN', 'WEAK_DOWN']:
                confidence += (abs(pre_score) / 5.0) * 0.5
            version_2_decision = 'SELL' if confidence >= 0.70 else None

        # VERSION 3: PRIORITY SYSTEM (Pre-candle güçlüyse eşik düşür)
        version_3_decision = signal  # Varsayılan: İndikatör kararı
        if pre_signal == 'STRONG_UP':
            if signal == 'BUY':
                buy_votes = min(10, int(buy_votes * 1.5))  # 50% boost
            elif buy_votes >= 2:  # Düşük eşik
                version_3_decision = 'BUY'
                buy_votes = max(3, buy_votes)
        elif pre_signal == 'STRONG_DOWN':
            if signal == 'SELL':
                sell_votes = min(10, int(sell_votes * 1.5))
            elif sell_votes >= 2:
                version_3_decision = 'SELL'
                sell_votes = max(3, sell_votes)

        # Log kararları (sadece bilgilendirme)
        if pre_signal != 'NEUTRAL':
            add_log(f"📊 {symbol} HYBRID KARAR: V1={version_1_decision}, V2={version_2_decision}, V3={version_3_decision} | Pre={pre_signal}, Ind={signal}", "HYBRID")

        # ŞİMDİLİK VERSION 3 KULLAN (Priority System)
        # Diğer versiyonlar arka planda metrik topluyor
        signal = version_3_decision

    return signal, buy_votes, sell_votes

def open_long(symbol, price, votes=5):
    """LONG pozisyon aç"""
    # VOLATİLİTE KONTROLÜ - Çok durgun veya çılgın coinleri filtrele
    if not check_volatility(symbol):
        return False  # Volatilite uygun değil, işlem yapma

    # POZİSYON BÜYÜKLÜĞÜ - Oy sayısına göre dinamik miktar
    if POSITION_SIZING_ENABLED:
        position_amount = POSITION_SIZE_BY_VOTES.get(votes, 25)  # Varsayılan $25
    else:
        position_amount = TRADE_AMOUNT

    if state['balance'] < position_amount:
        add_log(f"❌ Yetersiz bakiye: ${state['balance']:.2f}", "ERROR")
        return False

    quantity = position_amount / price

    # Pozisyon oluştur
    # SL hesaplaması: Dar trigger (0.6%) + Slippage buffer (0.2%) = Max zarar 0.8%
    position = {
        'symbol': symbol,
        'type': 'LONG',
        'entry_price': price,
        'quantity': quantity,
        'cost': position_amount,  # Pozisyon maliyeti (dashboard için)
        'stop_loss': price * (1 - STOP_LOSS_PERCENT),  # 0.6% trigger
        'take_profit': price * (1 + TAKE_PROFIT_PERCENT),
        'highest_price': price,  # Trailing TP için
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'leverage': FUTURES_LEVERAGE,
        'votes': votes  # Kaç indikatör onayladı
    }

    # KOMİSYON KESİNTİSİ (açılış) - Futures'da komisyon notional value üzerinden alınır
    notional_value = position_amount * FUTURES_LEVERAGE  # Pozisyon değeri = margin * leverage
    commission = notional_value * COMMISSION_RATE
    state['balance'] -= commission
    state['total_commission'] += commission

    state['open_positions'].append(position)
    state['balance'] -= position_amount
    state['long_positions'] += 1  # LONG sayacını artır
    state['last_trade_time'] = time.time()  # Son işlem zamanını güncelle

    # Max zarar hesabı (Slippage buffer dahil)
    max_loss_pct = (STOP_LOSS_PERCENT + SLIPPAGE_BUFFER) * 100
    max_loss_usd = position_amount * (STOP_LOSS_PERCENT + SLIPPAGE_BUFFER) * FUTURES_LEVERAGE
    add_log(f"📈 LONG AÇILDI: {symbol} @ ${price:.6f} | {quantity:.4f} ({votes}/10 oy, ${position_amount}) | SL: ${position['stop_loss']:.6f} (max -%{max_loss_pct:.1f} = ${max_loss_usd:.2f}) | TP: ${position['take_profit']:.6f}", "TRADE")
    return True

def open_short(symbol, price, votes=5):
    """SHORT pozisyon aç"""
    # VOLATİLİTE KONTROLÜ - Çok durgun veya çılgın coinleri filtrele
    if not check_volatility(symbol):
        return False  # Volatilite uygun değil, işlem yapma

    # POZİSYON BÜYÜKLÜĞÜ - Oy sayısına göre dinamik miktar
    if POSITION_SIZING_ENABLED:
        position_amount = POSITION_SIZE_BY_VOTES.get(votes, 25)  # Varsayılan $25
    else:
        position_amount = TRADE_AMOUNT

    if state['balance'] < position_amount:
        add_log(f"❌ Yetersiz bakiye: ${state['balance']:.2f}", "ERROR")
        return False

    quantity = position_amount / price

    # Pozisyon oluştur
    # SL hesaplaması: Dar trigger (0.6%) + Slippage buffer (0.2%) = Max zarar 0.8%
    position = {
        'symbol': symbol,
        'type': 'SHORT',
        'entry_price': price,
        'quantity': quantity,
        'cost': position_amount,  # Pozisyon maliyeti (dashboard için)
        'stop_loss': price * (1 + STOP_LOSS_PERCENT),  # SHORT için ters, 0.6% trigger
        'take_profit': price * (1 - TAKE_PROFIT_PERCENT),  # SHORT için ters
        'lowest_price': price,  # Trailing TP için
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'leverage': FUTURES_LEVERAGE,
        'votes': votes  # Kaç indikatör onayladı
    }

    # KOMİSYON KESİNTİSİ (açılış) - Futures'da komisyon notional value üzerinden alınır
    notional_value = position_amount * FUTURES_LEVERAGE  # Pozisyon değeri = margin * leverage
    commission = notional_value * COMMISSION_RATE
    state['balance'] -= commission
    state['total_commission'] += commission

    state['open_positions'].append(position)
    state['balance'] -= position_amount
    state['short_positions'] += 1  # SHORT sayacını artır
    state['last_trade_time'] = time.time()  # Son işlem zamanını güncelle

    # Max zarar hesabı (Slippage buffer dahil)
    max_loss_pct = (STOP_LOSS_PERCENT + SLIPPAGE_BUFFER) * 100
    max_loss_usd = position_amount * (STOP_LOSS_PERCENT + SLIPPAGE_BUFFER) * FUTURES_LEVERAGE
    add_log(f"📉 SHORT AÇILDI: {symbol} @ ${price:.6f} | {quantity:.4f} ({votes}/10 oy, ${position_amount}) | SL: ${position['stop_loss']:.6f} (max -%{max_loss_pct:.1f} = ${max_loss_usd:.2f}) | TP: ${position['take_profit']:.6f}", "TRADE")
    return True

def check_positions():
    """Açık pozisyonları kontrol et - Yeni: Trailing SL + Break-Even Stop"""
    for position in state['open_positions'][:]:
        symbol = position['symbol']
        current_price = get_price(symbol)

        if current_price is None:
            continue

        entry_price = position['entry_price']

        # Pozisyon açılma zamanı (timestamp string'i datetime'a çevir)
        position_time = datetime.strptime(position['timestamp'], "%Y-%m-%d %H:%M:%S")
        time_open_minutes = (datetime.now() - position_time).total_seconds() / 60

        # LONG pozisyon kontrolü
        if position['type'] == 'LONG':
            # Kar/Zarar hesapla
            profit_pct = (current_price - entry_price) / entry_price

            # 🔥 YENİ: BREAK-EVEN STOP (5dk sonra %0.5+ karda SL'yi break-even'a çek)
            # SADECE KARLI POZİSYONLARDA ÇALIŞIR!
            if BREAK_EVEN_ENABLED and profit_pct >= BREAK_EVEN_MIN_PROFIT_PCT:
                if time_open_minutes >= BREAK_EVEN_TIME_MINUTES:
                    # SL henüz break-even'a çekilmemişse çek
                    if position['stop_loss'] < entry_price:
                        position['stop_loss'] = entry_price
                        add_log(f"🛡️ {symbol} BREAK-EVEN STOP: SL → ${entry_price:.6f} (5dk + %{profit_pct*100:.1f} kar)", "TRAIL")

            # 🔥 v7.2: GERÇEK TRAILING STOP LOSS (kar edince SL'yi SÜREKLI yukarı çek)
            # KRİTİK: SADECE KARLI POZİSYONLARDA ÇALIŞIR! (profit_pct > 0)
            if TRAILING_SL_ENABLED and profit_pct > 0:
                if TRAILING_SL_MODE == "continuous":
                    # GERÇEK TRAİLİNG: Zirveden %0.5 uzaklıkta SL
                    # highest_price sürekli güncelleniyor, SL zirveyi %0.5 mesafede takip ediyor
                    new_sl = position['highest_price'] * (1 - TRAILING_SL_DISTANCE_PCT)

                    # SL'yi sadece yukarı çek (aşağı çekme)
                    if new_sl > position['stop_loss']:
                        old_sl = position['stop_loss']
                        position['stop_loss'] = new_sl
                        add_log(f"📈 {symbol} TRAILING SL: ${old_sl:.6f} → ${new_sl:.6f} (Zirve: ${position['highest_price']:.6f}, %{profit_pct*100:.2f} kar)", "TRAIL")
                else:
                    # ESKİ SISTEM: 3 seviyeli trailing (artık kullanılmıyor)
                    for level in reversed(TRAILING_SL_LEVELS):
                        if profit_pct >= level['profit_pct']:
                            new_sl = entry_price * (1 + level['sl_pct'])
                            if new_sl > position['stop_loss']:
                                old_sl = position['stop_loss']
                                position['stop_loss'] = new_sl
                                add_log(f"📈 {symbol} TRAILING SL: ${old_sl:.6f} → ${new_sl:.6f} (%{profit_pct*100:.1f} karda)", "TRAIL")
                            break

            # Stop Loss kontrolü (yeni SL ile)
            if current_price <= position['stop_loss']:
                loss_pct = ((current_price - entry_price) / entry_price) * 100
                close_position(position, current_price, f"STOP LOSS {loss_pct:+.1f}%")
                continue

            # Trailing TP: Fiyat belirtilen yüzde kadar yükseldi mi kontrol et
            if current_price >= entry_price * (1 + TRAILING_TP_ACTIVATION_PERCENT):
                # Her taramada en yüksek fiyatı güncelle
                current_highest = position.get('highest_price', entry_price)
                if current_price > current_highest:
                    position['highest_price'] = current_price
                    trailing_price = current_price * (1 - TRAILING_TP_DISTANCE_PERCENT)
                    add_log(f"🔝 {symbol} Yeni Zirve: ${current_price:.6f} (Trailing: ${trailing_price:.6f})", "INFO")

                # Trailing TP: Güncel en yüksekten belirtilen yüzde kadar düşme
                trailing_tp = position['highest_price'] * (1 - TRAILING_TP_DISTANCE_PERCENT)
                if current_price <= trailing_tp:
                    profit_pct_tp = ((position['highest_price'] - entry_price) / entry_price) * 100
                    close_position(position, current_price, f"TRAILING TP (Zirve: {profit_pct_tp:.1f}%)")

        # SHORT pozisyon kontrolü
        elif position['type'] == 'SHORT':
            # Kar/Zarar hesapla
            profit_pct = (entry_price - current_price) / entry_price

            # 🔥 YENİ: BREAK-EVEN STOP (5dk sonra %0.5+ karda SL'yi break-even'a çek)
            # SADECE KARLI POZİSYONLARDA ÇALIŞIR!
            if BREAK_EVEN_ENABLED and profit_pct >= BREAK_EVEN_MIN_PROFIT_PCT:
                if time_open_minutes >= BREAK_EVEN_TIME_MINUTES:
                    # SL henüz break-even'a çekilmemişse çek
                    if position['stop_loss'] > entry_price:
                        position['stop_loss'] = entry_price
                        add_log(f"🛡️ {symbol} BREAK-EVEN STOP: SL → ${entry_price:.6f} (5dk + %{profit_pct*100:.1f} kar)", "TRAIL")

            # 🔥 v7.2: GERÇEK TRAILING STOP LOSS (kar edince SL'yi SÜREKLI aşağı çek)
            # KRİTİK: SADECE KARLI POZİSYONLARDA ÇALIŞIR! (profit_pct > 0)
            if TRAILING_SL_ENABLED and profit_pct > 0:
                if TRAILING_SL_MODE == "continuous":
                    # GERÇEK TRAİLİNG: En düşükten %0.5 yukarıda SL
                    # lowest_price sürekli güncelleniyor, SL dibi %0.5 mesafede takip ediyor
                    new_sl = position['lowest_price'] * (1 + TRAILING_SL_DISTANCE_PCT)

                    # SL'yi sadece aşağı çek (yukarı çekme)
                    if new_sl < position['stop_loss']:
                        old_sl = position['stop_loss']
                        position['stop_loss'] = new_sl
                        add_log(f"📉 {symbol} TRAILING SL: ${old_sl:.6f} → ${new_sl:.6f} (Dip: ${position['lowest_price']:.6f}, %{profit_pct*100:.2f} kar)", "TRAIL")
                else:
                    # ESKİ SISTEM: 3 seviyeli trailing (artık kullanılmıyor)
                    for level in reversed(TRAILING_SL_LEVELS):
                        if profit_pct >= level['profit_pct']:
                            new_sl = entry_price * (1 - level['sl_pct'])
                            if new_sl < position['stop_loss']:
                                old_sl = position['stop_loss']
                                position['stop_loss'] = new_sl
                                add_log(f"📉 {symbol} TRAILING SL: ${old_sl:.6f} → ${new_sl:.6f} (%{profit_pct*100:.1f} karda)", "TRAIL")
                            break

            # Stop Loss kontrolü (yeni SL ile)
            if current_price >= position['stop_loss']:
                loss_pct = ((entry_price - current_price) / entry_price) * 100
                close_position(position, current_price, f"STOP LOSS {loss_pct:+.1f}%")
                continue

            # Trailing TP: Fiyat belirtilen yüzde kadar düştü mü kontrol et
            if current_price <= entry_price * (1 - TRAILING_TP_ACTIVATION_PERCENT):
                # Her taramada en düşük fiyatı güncelle
                current_lowest = position.get('lowest_price', entry_price)
                if current_price < current_lowest:
                    position['lowest_price'] = current_price
                    trailing_price = current_price * (1 + TRAILING_TP_DISTANCE_PERCENT)
                    add_log(f"🔻 {symbol} Yeni Dip: ${current_price:.6f} (Trailing: ${trailing_price:.6f})", "INFO")

                # Trailing TP: Güncel en düşükten belirtilen yüzde kadar yükselme
                trailing_tp = position['lowest_price'] * (1 + TRAILING_TP_DISTANCE_PERCENT)
                if current_price >= trailing_tp:
                    profit_pct_tp = ((entry_price - position['lowest_price']) / entry_price) * 100
                    close_position(position, current_price, f"TRAILING TP (Dip: {profit_pct_tp:.1f}%)")

def save_trade_to_csv(trade_record, position):
    """
    Her trade'i kalıcı CSV dosyasına kaydet
    Dosya yoksa oluştur, varsa ekle
    Her bilgi ayrı sütunda - kullanıcı talebi
    """
    csv_file = 'bot_trades_history.csv'
    file_exists = os.path.exists(csv_file)

    # Sütun başlıkları (her bilgi ayrı sütunda)
    fieldnames = ['Tarih', 'Saat', 'Coin', 'Tip', 'Giris_Fiyati', 'Cikis_Fiyati',
                  'Miktar', 'Leverage', 'PnL', 'Sebep', 'Sonuc', 'Oy_Sayisi']

    try:
        with open(csv_file, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            # İlk kez oluşturuluyorsa başlık ekle
            if not file_exists:
                writer.writeheader()

            # Tarihi saat ve tarih olarak ayır
            timestamp = trade_record['timestamp']
            tarih = timestamp.split()[0]
            saat = timestamp.split()[1]

            pnl = trade_record['pnl']
            sonuc = 'KAR' if pnl >= 0 else 'ZARAR'

            writer.writerow({
                'Tarih': tarih,
                'Saat': saat,
                'Coin': trade_record['symbol'],
                'Tip': trade_record['type'],
                'Giris_Fiyati': f"{trade_record['entry_price']:.8f}",
                'Cikis_Fiyati': f"{trade_record['exit_price']:.8f}",
                'Miktar': f"{position.get('quantity', 0):.8f}",
                'Leverage': f"{FUTURES_LEVERAGE}x",
                'PnL': f"{pnl:.2f}",
                'Sebep': trade_record['reason'],
                'Sonuc': sonuc,
                'Oy_Sayisi': position.get('votes', '')
            })
    except Exception as e:
        # Hata olursa logla ama botu durdurma
        add_log(f"CSV kayit hatasi: {e}", "ERROR")

def close_position(position, exit_price, reason):
    """Pozisyonu kapat"""
    symbol = position['symbol']

    # P&L hesapla
    if position['type'] == 'LONG':
        pnl = (exit_price - position['entry_price']) * position['quantity'] * FUTURES_LEVERAGE
    else:  # SHORT
        pnl = (position['entry_price'] - exit_price) * position['quantity'] * FUTURES_LEVERAGE

    # Kapanış komisyonu - Futures'da komisyon notional value üzerinden alınır
    notional_value = position['cost'] * FUTURES_LEVERAGE  # Pozisyon değeri = margin * leverage
    commission = notional_value * COMMISSION_RATE
    state['balance'] -= commission
    state['total_commission'] += commission

    # Bakiyeyi güncelle
    state['balance'] += position['cost'] + pnl  # cost = açılışta kullanılan miktar
    state['total_pnl'] += pnl

    # İstatistik güncelle
    if pnl > 0:
        state['winning_trades'] += 1
        result_icon = "✅"
    else:
        state['losing_trades'] += 1
        result_icon = "❌"

    # Trade history'e ekle
    trade_record = {
        'symbol': symbol,
        'type': position['type'],
        'entry_price': position['entry_price'],
        'exit_price': exit_price,
        'pnl': pnl,
        'reason': reason,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    state['trade_history'].insert(0, trade_record)

    # KALICI CSV KAYDI - Her işlem otomatik olarak dosyaya eklenir
    save_trade_to_csv(trade_record, position)

    # COİN PERFORMANS GÜNCELLEMESI (Adaptif öğrenme)
    if state['learning_active']:
        update_coin_performance(state, symbol, pnl)

    # LONG/SHORT sayacını azalt
    if position['type'] == 'LONG':
        state['long_positions'] = max(0, state['long_positions'] - 1)
    else:
        state['short_positions'] = max(0, state['short_positions'] - 1)

    # COİN COOLDOWN - Sebebe göre farklı bekleme süreleri
    base_hours = COOLDOWN_MULTIPLIER['base_hours']

    # Reason'dan cooldown type'ı belirle
    if "STOP LOSS" in reason.upper():
        multiplier = COOLDOWN_MULTIPLIER['stop_loss']  # 3x (6 saat) - Kötü coin, uzak dur!
    elif "TAKE PROFIT" in reason.upper() or "TP" in reason.upper():
        multiplier = COOLDOWN_MULTIPLIER['take_profit']  # 1x (2 saat) - İyi coin, tekrar dene
    elif "IDLE PROFIT" in reason.upper():
        multiplier = COOLDOWN_MULTIPLIER['idle_profit']  # 1.5x (3 saat) - Orta düzey
    else:
        multiplier = 1.0  # Default 2 saat

    cooldown_hours = base_hours * multiplier
    cooldown_until = time.time() + (cooldown_hours * 3600)
    state['coin_cooldown'][symbol] = cooldown_until
    cooldown_time = datetime.fromtimestamp(cooldown_until).strftime("%H:%M")

    # Pozisyonu kaldır
    state['open_positions'].remove(position)

    add_log(f"{result_icon} {position['type']} KAPANDI: {symbol} | Giriş: ${position['entry_price']:.6f} | Çıkış: ${exit_price:.6f} | P&L: ${pnl:.2f} | Komisyon: ${commission:.4f} | Sebep: {reason} | Cooldown: {cooldown_time}'e kadar", "TRADE")

# ============================================================================
# TRADING LOOP
# ============================================================================

def trading_loop():
    """Ana trading döngüsü"""
    add_log("🤖 Trading bot başlatıldı!")
    state['running'] = True
    state['connected'] = True

    while state['running']:
        try:
            state['scan_count'] += 1

            # PİYASA TRENDİNİ GÜNCELLE (Her 60 saniyede bir)
            update_market_trend(state)

            # PERFORMANS ANALİZİ (Adaptif öğrenme - Her 10 işlemde bir)
            if state['learning_active']:
                analysis_result = analyze_performance(state, {
                    'ANALYSIS_INTERVAL': ANALYSIS_INTERVAL,
                    'TARGET_WIN_RATE': TARGET_WIN_RATE
                })
                if analysis_result:
                    add_log(f"📊 ADAPTİF ANALİZ: {analysis_result['wins']}W-{analysis_result['losses']}L | "
                           f"Win Rate: {analysis_result['win_rate']:.1%} | "
                           f"Threshold: {analysis_result['old_threshold']} → {analysis_result['new_threshold']} | "
                           f"{analysis_result['reason']}", "INFO")

            # Açık pozisyonları kontrol et
            check_positions()

            # 5 DAKİKA IDLE PROFIT-TAKING KONTROLÜ
            time_since_last_trade = time.time() - state['last_trade_time']
            if time_since_last_trade >= (IDLE_PROFIT_CLOSE_MINUTES * 60):
                # 5 dakikadır işlem yok, $1+ kardakileri kapat
                profitable_positions = []
                for pos in state['open_positions']:
                    current_price = get_price(pos['symbol'])
                    if current_price:
                        if pos['type'] == 'LONG':
                            unrealized_pnl = (current_price - pos['entry_price']) * pos['quantity'] * FUTURES_LEVERAGE
                        else:
                            unrealized_pnl = (pos['entry_price'] - current_price) * pos['quantity'] * FUTURES_LEVERAGE

                        # $1+ karda mı?
                        if unrealized_pnl >= IDLE_PROFIT_THRESHOLD:
                            # ✅ KONTROL: Take profit tetiklenmiş mi?
                            tp_triggered = False

                            if pos['type'] == 'LONG':
                                # LONG: Fiyat TP seviyesine ulaştı mı?
                                take_profit_price = pos['entry_price'] * (1 + TAKE_PROFIT_PERCENT)
                                if current_price >= take_profit_price:
                                    tp_triggered = True
                            else:  # SHORT
                                # SHORT: Fiyat TP seviyesine ulaştı mı?
                                take_profit_price = pos['entry_price'] * (1 - TAKE_PROFIT_PERCENT)
                                if current_price <= take_profit_price:
                                    tp_triggered = True

                            # TP tetiklenmemişse idle kapatmaya ekle
                            if not tp_triggered:
                                profitable_positions.append((pos, current_price, unrealized_pnl))
                            else:
                                add_log(f"   {pos['symbol']} $1+ karda ama TP tetiklenmis, limit emrini bekliyor", "INFO")

                if profitable_positions:
                    add_log(f"⏰ 5dk idle, {len(profitable_positions)} pozisyon ${IDLE_PROFIT_THRESHOLD}+ karda (TP tetiklenmemis), kapatiliyor...", "INFO")
                    for pos, price, pnl in profitable_positions:
                        close_position(pos, price, f"IDLE PROFIT (${pnl:.2f})")

            # HİBRİT DİNAMİK LİSTE - TAM MARKET TARAMASI (Her 60 saniyede bir)
            if DYNAMIC_COIN_LIST:
                time_since_last_scan = time.time() - state['last_full_scan_time']
                if time_since_last_scan >= FULL_SCAN_INTERVAL:
                    full_market_scan()

            # ADIM 1: Tüm coinleri tara ve sinyalleri topla
            all_signals = []
            min_votes = state['current_min_votes'] if state['learning_active'] else MIN_INDICATOR_VOTES

            # Dinamik liste aktifse onu kullan, değilse static TRADING_PAIRS
            coins_to_scan = state['active_coin_list'] if DYNAMIC_COIN_LIST else TRADING_PAIRS

            for symbol in coins_to_scan:
                if not state['running']:
                    break

                # Zaten bu coin'de pozisyon var mı?
                has_position = any(p['symbol'] == symbol for p in state['open_positions'])
                if has_position:
                    continue

                # COİN COOLDOWN KONTROLÜ - 2 saat bekleme
                if symbol in state['coin_cooldown']:
                    cooldown_until = state['coin_cooldown'][symbol]
                    if time.time() < cooldown_until:
                        continue
                    else:
                        del state['coin_cooldown'][symbol]

                # 10 indikatörü kontrol et
                signal, buy_votes, sell_votes = check_10_indicator_signals(symbol)

                # v7.2: PİYASA TRENDİNE GÖRE GÜÇLÜ ÖNCELİKLENDİRME (HIZLI KARAR!)
                if MARKET_TREND_ENABLED:
                    market_trend = state['market_trend']
                    original_buy = buy_votes
                    original_sell = sell_votes

                    if market_trend == 'BULLISH':
                        # 🚀 Yükseliş trendinde: LONG sinyalleri 3x güçlü, SHORT sinyalleri AZALT (IPTAL ETME!)
                        buy_votes = min(10, int(buy_votes * MARKET_TREND_LONG_MULTIPLIER))
                        sell_votes = max(1, int(sell_votes * 0.6))  # %40 azalt ama IPTAL ETME!
                        if original_buy > 0 and buy_votes > original_buy:
                            add_log(f"🚀 {symbol} LONG BOOST: {original_buy} → {buy_votes} oy (BULLISH market)", "BOOST")
                    elif market_trend == 'BEARISH':
                        # 📉 Düşüş trendinde: SHORT sinyalleri 3x güçlü, LONG sinyalleri AZALT (IPTAL ETME!)
                        sell_votes = min(10, int(sell_votes * MARKET_TREND_SHORT_MULTIPLIER))
                        buy_votes = max(1, int(buy_votes * 0.6))  # %40 azalt ama IPTAL ETME!
                        if original_sell > 0 and sell_votes > original_sell:
                            add_log(f"📉 {symbol} SHORT BOOST: {original_sell} → {sell_votes} oy (BEARISH market)", "BOOST")
                    # SIDEWAYS ise değişiklik yok

                # Min threshold'u geçen sinyalleri topla
                if signal == 'BUY' and buy_votes >= min_votes:
                    # ✅ HACİM YÖNÜ KONTROLÜ
                    volume_confirmed, reason = should_trade_with_volume_confirmation(symbol, 'BUY')
                    if volume_confirmed:
                        all_signals.append({
                            'symbol': symbol,
                            'type': 'LONG',
                            'votes': buy_votes,
                            'price': get_price(symbol)
                        })
                        state['signals_detected'] += 1
                    else:
                        add_log(f"   {symbol} BUY sinyali ATLA ({reason})", "INFO")

                elif signal == 'SELL' and sell_votes >= min_votes:
                    # ✅ HACİM YÖNÜ KONTROLÜ
                    volume_confirmed, reason = should_trade_with_volume_confirmation(symbol, 'SELL')
                    if volume_confirmed:
                        all_signals.append({
                            'symbol': symbol,
                            'type': 'SHORT',
                            'votes': sell_votes,
                            'price': get_price(symbol)
                        })
                        state['signals_detected'] += 1
                    else:
                        add_log(f"   {symbol} SELL sinyali ATLA ({reason})", "INFO")

            # ADIM 2: Sinyalleri oy sayısına göre SIRALA (En yüksek oy en üstte)
            all_signals.sort(key=lambda x: x['votes'], reverse=True)

            # ADIM 3: En yüksek oy alan coinlerden başlayarak işlem aç (Para bitene kadar)
            for sig in all_signals:
                if not state['running']:
                    break

                # Bakiye yeterli mi? (Dinamik pozisyon büyüklüğüne göre)
                next_position_size = POSITION_SIZE_BY_VOTES.get(sig['votes'], TRADE_AMOUNT)
                if state['balance'] < next_position_size:
                    break  # Para bitti, dur

                # Pozisyon limiti kontrolü
                if len(state['open_positions']) >= MAX_OPEN_POSITIONS:
                    break

                symbol = sig['symbol']
                price = sig['price']

                if price is None:
                    continue

                if sig['type'] == 'LONG':
                    add_log(f"🎯 {symbol} AL SİNYALİ: {sig['votes']}/10 indikatör (Min: {min_votes})", "INFO")
                    open_long(symbol, price, votes=sig['votes'])
                elif sig['type'] == 'SHORT':
                    add_log(f"🎯 {symbol} SAT SİNYALİ: {sig['votes']}/10 indikatör (Min: {min_votes})", "INFO")
                    open_short(symbol, price, votes=sig['votes'])

            # Bekleme
            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            add_log(f"❌ Trading loop hatası: {e}", "ERROR")
            time.sleep(5)

    add_log("🛑 Trading bot durduruldu!")
    state['connected'] = False

# ============================================================================
# FLASK API
# ============================================================================

app = Flask(__name__)
CORS(app)

@app.route('/')
def dashboard():
    """Dashboard HTML - basit"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>10 İndikatör Trading Bot</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial; background: #1a1a1a; color: #fff; margin: 0; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { background: #2a2a2a; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .stat-box { background: #2a2a2a; padding: 15px; border-radius: 8px; }
        .stat-label { color: #888; font-size: 12px; }
        .stat-value { font-size: 24px; font-weight: bold; margin-top: 5px; }
        .green { color: #00ff00; }
        .red { color: #ff4444; }
        button { padding: 12px 30px; font-size: 16px; border: none; border-radius: 6px; cursor: pointer; margin: 5px; transition: all 0.2s ease; font-weight: bold; }
        button:hover { transform: scale(1.05); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        button:active { transform: scale(0.95); box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
        .start-btn { background: #00ff00; color: #000; }
        .start-btn:hover { background: #00dd00; }
        .stop-btn { background: #ff4444; color: #fff; }
        .stop-btn:hover { background: #ff6666; }
        .pause-btn { background: #ff9900; color: #fff; }
        .pause-btn:hover { background: #ffaa00; }
        .close-profit-btn { background: #00aa00; color: #fff; }
        .close-profit-btn:hover { background: #00cc00; }
        .positions { background: #2a2a2a; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .history { background: #2a2a2a; padding: 20px; border-radius: 10px; margin-bottom: 20px; max-height: 400px; overflow-y: auto; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #444; }
        th { background: #333; position: sticky; top: 0; }
        .close-btn { background: #ff4444; color: #fff; padding: 5px 15px; font-size: 12px; border-radius: 4px; cursor: pointer; border: none; transition: all 0.2s ease; }
        .close-btn:hover { background: #ff6666; transform: scale(1.05); }
        .close-btn:active { transform: scale(0.95); }
        .profit { color: #00ff00; font-weight: bold; }
        .loss { color: #ff4444; font-weight: bold; }
        .logs { background: #2a2a2a; padding: 20px; border-radius: 10px; max-height: 400px; overflow-y: auto; }
        .log-entry { padding: 8px; border-bottom: 1px solid #333; font-size: 13px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 10 İNDİKATÖR OYLAMA SİSTEMİ - TRADING BOT <span style="background:#ff9900;color:#000;padding:5px 10px;border-radius:5px;font-size:18px;margin-left:15px;">ID: """ + str(os.getpid()) + """</span></h1>
            <p>3/10 Kural: 3+ indikatör AL → LONG | 3+ indikatör SAT → SHORT</p>
            <button class="start-btn" id="toggle-btn" onclick="toggleBot()">▶ BAŞLAT</button>
            <button class="stop-btn" onclick="emergencyStop()">🚨 ACİL STOP</button>
            <button class="close-profit-btn" onclick="closeProfitablePositions()">💰 KARDA OLANLARI KAPAT</button>
        </div>

        <div class="stats">
            <div class="stat-box">
                <div class="stat-label">Bakiye</div>
                <div class="stat-value" id="balance">$0.00</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Toplam Bakiye</div>
                <div class="stat-value" id="total-balance">$0.00</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Toplam P&L</div>
                <div class="stat-value" id="total-pnl">$0.00</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Kazanma Oranı</div>
                <div class="stat-value" id="win-rate">0%</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Açık Pozisyon</div>
                <div class="stat-value" id="open-positions">0</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">İzlenen Coin</div>
                <div class="stat-value" id="coins">50</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Toplam Tarama</div>
                <div class="stat-value" id="scans">0</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Tespit Edilen Sinyal</div>
                <div class="stat-value" id="signals">0</div>
            </div>
        </div>

        <div class="positions">
            <h2>📊 Açık Pozisyonlar</h2>
            <table id="positions-table">
                <thead>
                    <tr>
                        <th>Sembol</th>
                        <th>Tip</th>
                        <th>Giriş Fiyatı</th>
                        <th>Adet</th>
                        <th>Maliyet</th>
                        <th>Anlık Fiyat</th>
                        <th>Anlık P&L</th>
                        <th>SL</th>
                        <th>TP</th>
                        <th>İşlem</th>
                    </tr>
                </thead>
                <tbody id="positions-body">
                    <tr><td colspan="10" style="text-align:center; color:#888;">Pozisyon yok</td></tr>
                </tbody>
            </table>
        </div>

        <div class="history">
            <h2>📜 İşlem Geçmişi (Son 20)</h2>
            <table id="history-table">
                <thead>
                    <tr>
                        <th>Zaman</th>
                        <th>Sembol</th>
                        <th>Tip</th>
                        <th>Giriş</th>
                        <th>Çıkış</th>
                        <th>P&L</th>
                        <th>Sebep</th>
                    </tr>
                </thead>
                <tbody id="history-body">
                    <tr><td colspan="7" style="text-align:center; color:#888;">Henüz işlem yok</td></tr>
                </tbody>
            </table>
        </div>

        <div class="logs">
            <h2>📝 Loglar</h2>
            <div id="logs-container"></div>
        </div>
    </div>

    <script>
        function updateData() {
            fetch('/api/data')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('balance').textContent = '$' + data.balance.toFixed(2);
                    document.getElementById('total-balance').textContent = '$' + data.total_balance.toFixed(2);
                    document.getElementById('total-pnl').textContent = '$' + data.total_pnl.toFixed(2);
                    document.getElementById('total-pnl').className = 'stat-value ' + (data.total_pnl >= 0 ? 'green' : 'red');
                    document.getElementById('win-rate').textContent = data.win_rate.toFixed(1) + '%';
                    document.getElementById('open-positions').textContent = data.open_positions.length;
                    document.getElementById('coins').textContent = data.total_coins_monitored;
                    document.getElementById('scans').textContent = data.active_scans;
                    document.getElementById('signals').textContent = data.signals_detected;

                    // Bot durumuna göre buton güncelle
                    let toggleBtn = document.getElementById('toggle-btn');
                    if (data.running) {
                        toggleBtn.textContent = '⏸ DURAKLAT';
                        toggleBtn.className = 'pause-btn';
                        botIsRunning = true; // Durumu güncelle
                    } else {
                        toggleBtn.textContent = '▶ BAŞLAT';
                        toggleBtn.className = 'start-btn';
                        botIsRunning = false; // Durumu güncelle
                    }

                    // Pozisyonlar
                    let tbody = document.getElementById('positions-body');
                    if (data.open_positions.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="10" style="text-align:center; color:#888;">Pozisyon yok</td></tr>';
                    } else {
                        tbody.innerHTML = data.open_positions.map((p, idx) => {
                            // Anlık fiyat ve P&L hesapla
                            let currentPrice = p.current_price || p.entry_price;
                            let cost = p.cost || 25; // Pozisyon maliyeti (backend'den gelen)
                            let pnl = 0;
                            if (p.type === 'LONG') {
                                pnl = (currentPrice - p.entry_price) * p.quantity * (p.leverage || 5);
                            } else {
                                pnl = (p.entry_price - currentPrice) * p.quantity * (p.leverage || 5);
                            }
                            let pnlClass = pnl >= 0 ? 'profit' : 'loss';
                            let pnlSign = pnl >= 0 ? '+' : '';

                            return `
                                <tr>
                                    <td>${p.symbol}</td>
                                    <td><span style="color: ${p.type === 'LONG' ? '#00ff00' : '#ff4444'}">${p.type}</span></td>
                                    <td>$${p.entry_price.toFixed(6)}</td>
                                    <td>${p.quantity.toFixed(4)}</td>
                                    <td>$${cost.toFixed(2)}</td>
                                    <td>$${currentPrice.toFixed(6)}</td>
                                    <td class="${pnlClass}">${pnlSign}$${pnl.toFixed(2)}</td>
                                    <td>$${p.stop_loss.toFixed(6)}</td>
                                    <td>$${p.take_profit.toFixed(6)}</td>
                                    <td><button class="close-btn" onclick="closePosition('${p.symbol}')">KAPAT</button></td>
                                </tr>
                            `;
                        }).join('');
                    }

                    // İşlem Geçmişi
                    let historyBody = document.getElementById('history-body');
                    if (data.trade_history.length === 0) {
                        historyBody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#888;">Henüz işlem yok</td></tr>';
                    } else {
                        historyBody.innerHTML = data.trade_history.map(trade => {
                            let pnlClass = trade.pnl >= 0 ? 'profit' : 'loss';
                            let pnlSign = trade.pnl >= 0 ? '+' : '';
                            return `
                                <tr>
                                    <td>${trade.timestamp}</td>
                                    <td>${trade.symbol}</td>
                                    <td><span style="color: ${trade.type === 'LONG' ? '#00ff00' : '#ff4444'}">${trade.type}</span></td>
                                    <td>$${trade.entry_price.toFixed(6)}</td>
                                    <td>$${trade.exit_price.toFixed(6)}</td>
                                    <td class="${pnlClass}">${pnlSign}$${trade.pnl.toFixed(2)}</td>
                                    <td>${trade.reason}</td>
                                </tr>
                            `;
                        }).join('');
                    }

                    // Loglar
                    let logsDiv = document.getElementById('logs-container');
                    logsDiv.innerHTML = data.logs.map(log => `
                        <div class="log-entry">[${log.time}] ${log.message}</div>
                    `).reverse().join('');
                });
        }

        // Global değişken: Bot durumunu takip et
        let botIsRunning = false;

        function toggleBot() {
            console.log('[TOGGLE] Buton basildi');

            // Önce sunucudan gerçek durumu al ve ona göre karar ver
            fetch('/api/data')
                .then(r => r.json())
                .then(data => {
                    const currentlyRunning = data.running;
                    console.log('[TOGGLE] Mevcut bot durumu:', currentlyRunning ? 'CALISIYOR' : 'DURDURULMUS');

                    // Bot çalışıyorsa STOP işlemi → Onay iste
                    if (currentlyRunning) {
                        console.log('[TOGGLE] Bot calisiyor, onay penceresi gosteriliyor');
                        if (!confirm('Botu durdurmak istediginize emin misiniz?\\n\\nAcik pozisyonlar kapatilmayacak, sadece yeni islem acilmayacak.')) {
                            console.log('[TOGGLE] Kullanici iptal etti');
                            return; // İptal edildi
                        }
                        console.log('[TOGGLE] Kullanici onayladi, bot durduruluyor');
                    } else {
                        console.log('[TOGGLE] Bot durdurulmus, baslatiliyor');
                    }

                    // İşlemi gerçekleştir
                    fetch('/api/toggle', {method: 'POST'})
                        .then(r => r.json())
                        .then(data => {
                            if (data.success) {
                                console.log('[TOGGLE] Basarili:', data.message);
                                console.log('[TOGGLE] Yeni durum:', data.running ? 'CALISIYOR' : 'DURDURULMUS');
                                botIsRunning = data.running; // Durumu güncelle
                            } else {
                                console.error('[TOGGLE] Basarisiz:', data);
                            }
                        })
                        .catch(err => {
                            console.error('[TOGGLE] API hatasi:', err);
                        });
                })
                .catch(err => {
                    console.error('[TOGGLE] Durum kontrolu hatasi:', err);
                });
        }

        function emergencyStop() {
            if (confirm('Tüm pozisyonları kapatıp botu durdurmak istediğinize emin misiniz?')) {
                fetch('/api/emergency_stop', {method: 'POST'})
                    .then(r => r.json())
                    .then(data => alert(data.closed_positions + ' pozisyon kapatıldı! Bot durduruldu.'));
            }
        }

        function closeProfitablePositions() {
            if (confirm('Karda olan tüm pozisyonları kapatmak istediğinize emin misiniz?')) {
                fetch('/api/close_profitable', {method: 'POST'})
                    .then(r => r.json())
                    .then(data => alert(data.closed_count + ' karda pozisyon kapatıldı! Toplam kar: $' + data.total_profit.toFixed(2)));
            }
        }

        function closePosition(symbol) {
            if (confirm(`${symbol} pozisyonunu kapatmak istediğinize emin misiniz?`)) {
                fetch('/api/close_position', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({symbol: symbol})
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        alert(`${symbol} pozisyonu kapatıldı! P&L: $${data.pnl.toFixed(2)}`);
                    } else {
                        alert('Hata: ' + data.message);
                    }
                });
            }
        }

        setInterval(updateData, 1000);
        updateData();
    </script>
</body>
</html>
    """
    return html

@app.route('/api/data')
def get_data():
    """Bot verileri"""
    # Unrealized P&L hesapla
    unrealized_pnl = 0
    for pos in state['open_positions']:
        current_price = get_price(pos['symbol'])
        if current_price:
            if pos['type'] == 'LONG':
                pnl = (current_price - pos['entry_price']) * pos['quantity'] * FUTURES_LEVERAGE
            else:
                pnl = (pos['entry_price'] - current_price) * pos['quantity'] * FUTURES_LEVERAGE
            unrealized_pnl += pnl

    total_balance = state['balance'] + unrealized_pnl

    # Win rate hesapla
    total_trades = state['winning_trades'] + state['losing_trades']
    win_rate = (state['winning_trades'] / total_trades * 100) if total_trades > 0 else 0

    # Pozisyonlara anlık fiyat ekle
    positions_with_price = []
    for pos in state['open_positions']:
        pos_copy = pos.copy()
        pos_copy['current_price'] = get_price(pos['symbol']) or pos['entry_price']
        positions_with_price.append(pos_copy)

    # Adaptif öğrenme metrikleri
    learning_metrics = get_learning_metrics(state) if state['learning_active'] else None

    return jsonify({
        'running': state['running'],
        'connected': state['connected'],
        'balance': round(state['balance'], 2),
        'unrealized_pnl': round(unrealized_pnl, 2),
        'total_balance': round(total_balance, 2),
        'total_pnl': round(state['total_pnl'], 2),
        'win_rate': round(win_rate, 2),
        'open_positions': positions_with_price,
        'trade_history': state['trade_history'][:20],
        'logs': state['logs'][-30:],
        'total_coins_monitored': len(state['active_coin_list']) if DYNAMIC_COIN_LIST else len(TRADING_PAIRS),
        'total_indicators': 10,
        'scan_interval': SCAN_INTERVAL,
        'active_scans': state['scan_count'],
        'signals_detected': state['signals_detected'],
        'demo_mode': DEMO_MODE,
        'learning_metrics': learning_metrics,
        'dynamic_list_stats': {
            'enabled': DYNAMIC_COIN_LIST,
            'active_coins': len(state['active_coin_list']),
            'total_scans': state['dynamic_list_stats']['total_scans'],
            'coins_added': state['dynamic_list_stats']['coins_added'],
            'coins_removed': state['dynamic_list_stats']['coins_removed'],
            'pumps_detected': state['dynamic_list_stats']['pumps_detected'],
            'pump_list': state['pump_detected_coins'][:10]  # İlk 10 pump
        } if DYNAMIC_COIN_LIST else None
    })

@app.route('/api/toggle', methods=['POST'])
def toggle_bot():
    """Botu başlat/durdur"""
    if not state['running']:
        add_log("🟢 START butonu basıldı, trading_loop başlatılıyor...")
        threading.Thread(target=trading_loop, daemon=True).start()
        return jsonify({'success': True, 'message': 'Bot başlatıldı', 'running': True})
    else:
        add_log("🔴 STOP butonu basıldı, bot duraklatılıyor...")
        state['running'] = False
        return jsonify({'success': True, 'message': 'Bot duraklatıldı', 'running': False})

@app.route('/api/emergency_stop', methods=['POST'])
def emergency_stop():
    """Tüm pozisyonları kapat ve botu durdur"""
    closed_count = 0
    for position in state['open_positions'][:]:
        price = get_price(position['symbol'])
        if price:
            close_position(position, price, "EMERGENCY STOP")
            closed_count += 1

    # Botu durdur
    state['running'] = False

    return jsonify({
        'success': True,
        'closed_positions': closed_count,
        'new_balance': round(state['balance'], 2)
    })

@app.route('/api/close_profitable', methods=['POST'])
def close_profitable_positions():
    """Karda olan tüm pozisyonları kapat"""
    closed_count = 0
    total_profit = 0

    for position in state['open_positions'][:]:
        price = get_price(position['symbol'])
        if not price:
            continue

        # P&L hesapla
        if position['type'] == 'LONG':
            pnl = (price - position['entry_price']) * position['quantity'] * FUTURES_LEVERAGE
        else:
            pnl = (position['entry_price'] - price) * position['quantity'] * FUTURES_LEVERAGE

        # Karda ise kapat
        if pnl > 0:
            close_position(position, price, "KARDA KAPATMA")
            closed_count += 1
            total_profit += pnl

    return jsonify({
        'success': True,
        'closed_count': closed_count,
        'total_profit': round(total_profit, 2)
    })

@app.route('/api/close_position', methods=['POST'])
def close_position_api():
    """Tek pozisyonu kapat"""
    from flask import request
    data = request.get_json()
    symbol = data.get('symbol')

    # Pozisyonu bul
    position = None
    for p in state['open_positions']:
        if p['symbol'] == symbol:
            position = p
            break

    if not position:
        return jsonify({'success': False, 'message': 'Pozisyon bulunamadı'})

    # Anlık fiyatı al ve kapat
    price = get_price(symbol)
    if not price:
        return jsonify({'success': False, 'message': 'Fiyat alınamadı'})

    # P&L hesapla
    if position['type'] == 'LONG':
        pnl = (price - position['entry_price']) * position['quantity'] * FUTURES_LEVERAGE
    else:
        pnl = (position['entry_price'] - price) * position['quantity'] * FUTURES_LEVERAGE

    close_position(position, price, "MANUEL KAPATMA")

    return jsonify({
        'success': True,
        'pnl': pnl,
        'close_price': price
    })

def run_flask():
    """Flask server'ı başlat"""
    import os
    port = int(os.environ.get('PORT', 5000))  # Render dinamik port desteği
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("🤖 10 İNDİKATÖR OYLAMA SİSTEMİ - TRADING BOT")
    print("=" * 80)
    print(f"📊 Takip Edilen Coin: {len(TRADING_PAIRS)} adet")
    print(f"🎯 İndikatör Sayısı: 10 adet")
    print(f"✅ AL Kuralı: 3+ indikatör AL sinyali → LONG aç")
    print(f"❌ SAT Kuralı: 3+ indikatör SAT sinyali → SHORT aç")
    print(f"💰 Başlangıç Bakiyesi: ${DEMO_BALANCE}")
    print(f"📈 İşlem Başına: ${TRADE_AMOUNT}")
    print(f"🔄 Tarama Aralığı: {SCAN_INTERVAL} saniye")
    print(f"⚡ Kaldıraç: {FUTURES_LEVERAGE}x")
    print(f"🎮 Demo Mode: {'AÇIK' if DEMO_MODE else 'KAPALI'}")
    print(f"🚀 Otomatik Başlatma: {'AÇIK' if AUTO_START else 'KAPALI (MANUEL)'}")
    print("=" * 80)
    print(f"\n📱 Dashboard: http://localhost:5000")
    print("=" * 80)

    # Flask server'ı başlat
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Tarayıcıyı aç
    time.sleep(2)
    webbrowser.open('http://localhost:5000')

    # Auto-start yoksa, manuel başlatma beklenir
    if AUTO_START:
        add_log("🚀 Otomatik başlatma aktif, bot başlatılıyor...")
        threading.Thread(target=trading_loop, daemon=True).start()
    else:
        add_log("⏸️ Manuel başlatma modu - Dashboard'dan 'Başlat' butonuna basın")

    # Ana thread'i canlı tut
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Bot kapatılıyor...")
        state['running'] = False
