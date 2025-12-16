#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PİYASA TRENDİ ALGILAMA MOD ÜLÜ (Yedek/Standalone Versiyon)

BTCUSDT referans alınarak piyasa trendini algılar:
- BULLISH (Yükseliş): LONG işlemler 2x ağırlıklı
- BEARISH (Düşüş): SHORT işlemler 2x ağırlıklı
- SIDEWAYS (Yatay): Normal işlem

Kullanım:
    from market_trend import update_market_trend

    state = {
        'market_trend': 'SIDEWAYS',
        'market_trend_strength': 0.0,
        'last_trend_check': 0,
        'trend_sma_fast': 0.0,
        'trend_sma_slow': 0.0
    }

    update_market_trend(state, config)
"""

import requests
import time

BASE_URL = "https://api.binance.com"

def update_market_trend(state, config=None):
    """
    PİYASA TRENDİNİ GÜNCELLE

    Args:
        state (dict): Bot state dictionary
        config (dict, optional): Configuration parameters
            {
                'ENABLED': True/False,
                'CHECK_INTERVAL': 60,  # seconds
                'REFERENCE_COIN': 'BTCUSDT',
                'PERIOD': 50,  # candles
                'LONG_MULTIPLIER': 2.0,
                'SHORT_MULTIPLIER': 2.0
            }

    Returns:
        bool: Güncelleme yapıldı mı?
    """
    # Varsayılan config
    if config is None:
        config = {
            'ENABLED': True,
            'CHECK_INTERVAL': 60,
            'REFERENCE_COIN': 'BTCUSDT',
            'PERIOD': 50,
            'LONG_MULTIPLIER': 2.0,
            'SHORT_MULTIPLIER': 2.0
        }

    if not config.get('ENABLED', True):
        return False

    current_time = time.time()

    # Her N saniyede bir kontrol et
    check_interval = config.get('CHECK_INTERVAL', 60)
    if current_time - state.get('last_trend_check', 0) < check_interval:
        return False

    try:
        # BTC kline verilerini al
        reference_coin = config.get('REFERENCE_COIN', 'BTCUSDT')
        period = config.get('PERIOD', 50)

        url = f"{BASE_URL}/api/v3/klines"
        params = {
            'symbol': reference_coin,
            'interval': '15m',
            'limit': period
        }

        response = requests.get(url, params=params, timeout=5)
        if response.status_code != 200:
            return False

        klines = response.json()

        # Kapanış fiyatlarını al
        close_prices = [float(k[4]) for k in klines]

        # SMA hesapla
        sma_fast = sum(close_prices[-20:]) / 20  # Hızlı: Son 20 mum (5 saat)
        sma_slow = sum(close_prices) / len(close_prices)  # Yavaş: Tüm mumlar

        # Trend gücü (%)
        strength = ((sma_fast - sma_slow) / sma_slow) * 100

        # Trend belirle
        if strength > 0.3:
            trend = 'BULLISH'
            emoji = '🟢'
        elif strength < -0.3:
            trend = 'BEARISH'
            emoji = '🔴'
        else:
            trend = 'SIDEWAYS'
            emoji = '🟡'

        # State'i güncelle
        old_trend = state.get('market_trend', 'SIDEWAYS')
        trend_changed = old_trend != trend

        state['market_trend'] = trend
        state['market_trend_strength'] = strength
        state['last_trend_check'] = current_time
        state['trend_sma_fast'] = sma_fast
        state['trend_sma_slow'] = sma_slow

        # Trend değişikliğini logla (opsiyonel)
        if trend_changed:
            print(f"{emoji} PİYASA TRENDİ: {old_trend} → {trend} (Güç: {strength:+.2f}%)")

            if trend == 'BULLISH':
                print(f"   📈 LONG işlemler {config.get('LONG_MULTIPLIER', 2.0)}x ağırlıklı")
            elif trend == 'BEARISH':
                print(f"   📉 SHORT işlemler {config.get('SHORT_MULTIPLIER', 2.0)}x ağırlıklı")
            else:
                print(f"   ➡️ Yatay piyasa, normal işlem")

        return True

    except Exception as e:
        print(f"⚠️ Trend güncelleme hatası: {e}")
        return False


def apply_trend_weighting(buy_votes, sell_votes, state, config=None):
    """
    SİNYALLERİ TREND'E GÖRE AĞIRLIKLANDIR

    Args:
        buy_votes (int): LONG sinyal oyları
        sell_votes (int): SHORT sinyal oyları
        state (dict): Bot state
        config (dict, optional): Config

    Returns:
        tuple: (weighted_buy_votes, weighted_sell_votes)
    """
    if config is None:
        config = {
            'ENABLED': True,
            'LONG_MULTIPLIER': 2.0,
            'SHORT_MULTIPLIER': 2.0
        }

    if not config.get('ENABLED', True):
        return buy_votes, sell_votes

    trend = state.get('market_trend', 'SIDEWAYS')

    if trend == 'BULLISH':
        # Yükseliş: LONG güçlü, SHORT zayıf
        long_mult = config.get('LONG_MULTIPLIER', 2.0)
        short_mult = config.get('SHORT_MULTIPLIER', 2.0)

        buy_votes = int(buy_votes * long_mult)
        sell_votes = int(sell_votes / short_mult)

    elif trend == 'BEARISH':
        # Düşüş: SHORT güçlü, LONG zayıf
        long_mult = config.get('LONG_MULTIPLIER', 2.0)
        short_mult = config.get('SHORT_MULTIPLIER', 2.0)

        sell_votes = int(sell_votes * short_mult)
        buy_votes = int(buy_votes / long_mult)

    return buy_votes, sell_votes


def get_trend_info(state):
    """
    MEVCUT TREND BİLGİSİNİ AL

    Args:
        state (dict): Bot state

    Returns:
        dict: Trend bilgileri
    """
    return {
        'trend': state.get('market_trend', 'SIDEWAYS'),
        'strength': state.get('market_trend_strength', 0.0),
        'sma_fast': state.get('trend_sma_fast', 0.0),
        'sma_slow': state.get('trend_sma_slow', 0.0),
        'last_update': state.get('last_trend_check', 0)
    }


# Test için
if __name__ == "__main__":
    print("=" * 60)
    print("PİYASA TRENDİ ALGILAMA MODÜLxÜ - TEST")
    print("=" * 60)

    # Test state
    state = {
        'market_trend': 'SIDEWAYS',
        'market_trend_strength': 0.0,
        'last_trend_check': 0,
        'trend_sma_fast': 0.0,
        'trend_sma_slow': 0.0
    }

    # Config
    config = {
        'ENABLED': True,
        'CHECK_INTERVAL': 0,  # Anında çalış
        'REFERENCE_COIN': 'BTCUSDT',
        'PERIOD': 50,
        'LONG_MULTIPLIER': 2.0,
        'SHORT_MULTIPLIER': 2.0
    }

    print("\n📊 Mevcut piyasa trendini kontrol ediliyor...")
    result = update_market_trend(state, config)

    if result:
        info = get_trend_info(state)
        print(f"\n✅ Trend Bilgileri:")
        print(f"   Trend: {info['trend']}")
        print(f"   Güç: {info['strength']:+.2f}%")
        print(f"   Fast SMA (20): ${info['sma_fast']:,.2f}")
        print(f"   Slow SMA (50): ${info['sma_slow']:,.2f}")

        # Sinyal ağırlıklandırma örneği
        print(f"\n🎯 Sinyal Ağırlıklandırma Örneği:")
        print(f"   Örnek: 5 LONG oy, 3 SHORT oy")

        weighted_buy, weighted_sell = apply_trend_weighting(5, 3, state, config)
        print(f"   Sonuç: {weighted_buy} LONG oy, {weighted_sell} SHORT oy")

        if info['trend'] == 'BULLISH':
            print(f"   → BULLISH trend: LONG sinyalleri güçlendirildi")
        elif info['trend'] == 'BEARISH':
            print(f"   → BEARISH trend: SHORT sinyalleri güçlendirildi")
        else:
            print(f"   → SIDEWAYS: Değişiklik yok")
    else:
        print("❌ Trend güncellenemedi")

    print("\n" + "=" * 60)
    print("✅ TEST TAMAMLANDI")
    print("=" * 60)
