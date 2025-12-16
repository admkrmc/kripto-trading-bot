#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADAPTİF ÖĞRENME SİSTEMİ
Her 10 işlemde bir performans analizi yapar ve indikatör eşiğini otomatik ayarlar
"""

import time
from datetime import datetime, timedelta

def analyze_performance(state, config):
    """
    Son 10 işlemi analiz et ve öğrenme yap

    Args:
        state: Bot'un global state'i
        config: Konfigürasyon değerleri (ANALYSIS_INTERVAL, TARGET_WIN_RATE, vb.)

    Returns:
        dict: Analiz sonuçları ve öneriler
    """
    trade_history = state['trade_history']
    total_trades = len(trade_history)

    # Her N işlemde bir analiz yap
    if total_trades < config['ANALYSIS_INTERVAL']:
        return None

    # Son analizden bu yana yeterli işlem oldu mu?
    if total_trades - state['last_analysis_trade_count'] < config['ANALYSIS_INTERVAL']:
        return None

    # Son 10 işlemi al (en yeniler BAŞTA olduğu için [:N] kullan)
    last_trades = trade_history[:config['ANALYSIS_INTERVAL']]

    # Performans metriklerini hesapla
    wins = sum(1 for t in last_trades if t['pnl'] > 0)
    losses = sum(1 for t in last_trades if t['pnl'] < 0)
    win_rate = wins / len(last_trades) if len(last_trades) > 0 else 0

    avg_win = sum(t['pnl'] for t in last_trades if t['pnl'] > 0) / wins if wins > 0 else 0
    avg_loss = sum(t['pnl'] for t in last_trades if t['pnl'] < 0) / losses if losses > 0 else 0
    total_pnl = sum(t['pnl'] for t in last_trades)

    # Mevcut threshold
    current_threshold = state['current_min_votes']
    old_threshold = current_threshold

    # Öğrenme: %50 hedefine göre threshold ayarla
    if not state['optimal_threshold_found']:
        if win_rate < (config['TARGET_WIN_RATE'] - 0.10):  # %40'ın altında → Daha muhafazakar ol
            # Çok fazla zarar → İndikatör eşiğini artır
            current_threshold = min(6, current_threshold + 1)
            reason = f"🔴 Çok fazla zarar ({win_rate:.1%})"

        elif win_rate > (config['TARGET_WIN_RATE'] + 0.10):  # %60'ın üstünde → Daha agresif ol
            # Çok iyi gidiyor → İndikatör eşiğini azalt
            current_threshold = max(2, current_threshold - 1)
            reason = f"🔵 Çok iyi gidiyor ({win_rate:.1%})"

        elif config['TARGET_WIN_RATE'] - 0.05 <= win_rate <= config['TARGET_WIN_RATE'] + 0.05:
            # İdeal aralıkta → Sabitle!
            state['optimal_threshold_found'] = True
            reason = f"🎯 Optimal seviye bulundu! ({win_rate:.1%})"

        else:
            # Kabul edilebilir aralıkta → Değiştirme
            reason = f"🟢 Kabul edilebilir ({win_rate:.1%})"

    else:
        # Optimal seviye bulundu, ama kötüye giderse tekrar ayarla
        if win_rate < (config['TARGET_WIN_RATE'] - 0.15):  # %35'in altında
            state['optimal_threshold_found'] = False
            current_threshold = min(6, current_threshold + 1)
            reason = f"⚠️ Optimal seviye bozuldu, yeniden ayarlanıyor ({win_rate:.1%})"
        else:
            reason = f"✅ Optimal seviyede devam ({win_rate:.1%})"

    # Threshold değişti mi?
    threshold_changed = current_threshold != old_threshold

    # State'i güncelle
    state['current_min_votes'] = current_threshold
    state['last_analysis_trade_count'] = total_trades

    if threshold_changed:
        state['threshold_history'].append({
            'timestamp': datetime.now().strftime("%H:%M:%S"),
            'old_threshold': old_threshold,
            'new_threshold': current_threshold,
            'win_rate': win_rate,
            'reason': reason
        })

    return {
        'analyzed': True,
        'total_trades_analyzed': len(last_trades),
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'total_pnl': total_pnl,
        'old_threshold': old_threshold,
        'new_threshold': current_threshold,
        'threshold_changed': threshold_changed,
        'optimal_found': state['optimal_threshold_found'],
        'reason': reason
    }


def update_coin_performance(state, symbol, pnl):
    """
    Coin bazında performansı güncelle

    Args:
        state: Bot'un global state'i
        symbol: Coin sembolü
        pnl: Kar/Zarar miktarı
    """
    if symbol not in state['coin_performance']:
        state['coin_performance'][symbol] = {
            'wins': 0,
            'losses': 0,
            'total_pnl': 0,
            'last_3_trades': []
        }

    perf = state['coin_performance'][symbol]

    if pnl > 0:
        perf['wins'] += 1
    else:
        perf['losses'] += 1

    perf['total_pnl'] += pnl
    perf['last_3_trades'].append(pnl)

    # Son 3 işlemi tut
    if len(perf['last_3_trades']) > 3:
        perf['last_3_trades'].pop(0)


def check_coin_blacklist(state, symbol, config):
    """
    Coin kara listede mi kontrol et ve gerekirse kara listeye ekle

    Args:
        state: Bot'un global state'i
        symbol: Coin sembolü
        config: Konfigürasyon (COIN_BLACKLIST_HOURS)

    Returns:
        bool: True ise kara listede (işlem yapma)
    """
    current_time = time.time()

    # Kara listede mi?
    if symbol in state['coin_blacklist']:
        blacklist_until = state['coin_blacklist'][symbol]
        if current_time < blacklist_until:
            return True  # Hala kara listede
        else:
            # Süre doldu, kara listeden çıkar
            del state['coin_blacklist'][symbol]

    # Performans kötü mü? Kara listeye ekle
    if symbol in state['coin_performance']:
        perf = state['coin_performance'][symbol]
        total_trades = perf['wins'] + perf['losses']

        # En az 3 işlem yapılmış olmalı
        if total_trades >= 3:
            win_rate = perf['wins'] / total_trades

            # %30'un altında win rate → Kara listeye ekle
            if win_rate < 0.30:
                blacklist_until = current_time + (config['COIN_BLACKLIST_HOURS'] * 3600)
                state['coin_blacklist'][symbol] = blacklist_until

                blacklist_time = datetime.fromtimestamp(blacklist_until).strftime("%H:%M")
                return {
                    'blacklisted': True,
                    'reason': f"Düşük win rate: {win_rate:.1%} ({perf['wins']}W/{perf['losses']}L)",
                    'until': blacklist_time
                }

    return False


def get_blacklist_info(state):
    """
    Kara liste bilgilerini al

    Returns:
        list: Kara listedeki coinler ve süreler
    """
    current_time = time.time()
    blacklist_info = []

    for symbol, until_timestamp in state['coin_blacklist'].items():
        if current_time < until_timestamp:
            remaining_hours = (until_timestamp - current_time) / 3600
            blacklist_info.append({
                'symbol': symbol,
                'until': datetime.fromtimestamp(until_timestamp).strftime("%H:%M"),
                'remaining_hours': remaining_hours
            })

    return sorted(blacklist_info, key=lambda x: x['remaining_hours'])


def get_learning_metrics(state):
    """
    Dashboard için öğrenme metriklerini hazırla

    Returns:
        dict: Öğrenme sistemi metrikleri
    """
    return {
        'adaptive_learning_active': state['learning_active'],
        'current_threshold': state['current_min_votes'],
        'optimal_found': state['optimal_threshold_found'],
        'blacklisted_coins': get_blacklist_info(state),
        'threshold_changes': len(state['threshold_history']),
        'last_threshold_change': state['threshold_history'][-1] if state['threshold_history'] else None,
        'coin_performance': {
            symbol: {
                'win_rate': perf['wins'] / (perf['wins'] + perf['losses']) if (perf['wins'] + perf['losses']) > 0 else 0,
                'total_trades': perf['wins'] + perf['losses'],
                'total_pnl': perf['total_pnl']
            }
            for symbol, perf in state['coin_performance'].items()
            if (perf['wins'] + perf['losses']) >= 3  # En az 3 işlem yapılmış olsun
        }
    }
