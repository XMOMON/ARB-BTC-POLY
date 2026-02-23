#!/usr/bin/env python3
"""
ALBERT POLYMARKET FAST-LOOP v3.0 (EXECUTION READY)
==================================================
Integrated with Simmer SDK for real-time Polymarket execution.
Handles BTC/ETH/SOL sprints based on momentum.
"""

import os
import sys
import json
import math
import argparse
import time
import io
import ssl
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

# Ignore SSL certificate errors
ssl_context = ssl._create_unverified_context()

# =============================================================================
# Configuration
# =============================================================================
SIMMER_API_KEY = os.getenv("SIMMER_API_KEY", "")
ASSET = os.getenv("SIMMER_SPRINT_ASSET", "BTC").upper()
WINDOW = os.getenv("SIMMER_SPRINT_WINDOW", "5m")
MIN_MOMENTUM_PCT = float(os.getenv("SIMMER_SPRINT_MOMENTUM", "0.5"))
MAX_POSITION = float(os.getenv("SIMMER_SPRINT_MAX_POSITION", "5.0"))

ASSET_SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
ASSET_PATTERNS = {"BTC": ["bitcoin up or down"], "ETH": ["ethereum up or down"], "SOL": ["solana up or down"]}
TRADE_SOURCE = "albert:fastloop"

# =============================================================================
# Simmer Integration
# =============================================================================
_client = None
def get_client():
    global _client
    if _client is None:
        try:
            from simmer_sdk import SimmerClient
        except ImportError:
            print("❌ simmer-sdk not installed.")
            return None
        
        if not SIMMER_API_KEY:
            print("❌ SIMMER_API_KEY not set in environment.")
            return None
            
        try:
            _client = SimmerClient(api_key=SIMMER_API_KEY, venue="polymarket")
        except Exception as e:
            print(f"❌ Failed to init SimmerClient: {e}")
            return None
    return _client

# =============================================================================
# API Helpers
# =============================================================================
def _api_request(url, method="GET", data=None, headers=None, timeout=15):
    try:
        req_headers = headers or {}
        if "User-Agent" not in req_headers:
            req_headers["User-Agent"] = "albert-fastloop/3.0"
        body = json.dumps(data).encode("utf-8") if data else None
        if data: req_headers["Content-Type"] = "application/json"
        req = Request(url, data=body, headers=req_headers, method=method)
        with urlopen(req, timeout=timeout, context=ssl_context) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

# =============================================================================
# Discovery & Momentum
# =============================================================================
def get_coingecko_price(asset="BTC"):
    cg_id = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}.get(asset, "bitcoin")
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd"
    result = _api_request(url)
    if result and cg_id in result:
        return result[cg_id]["usd"]
    return None

def get_momentum(asset="BTC", lookback=5):
    # Try Binance first (simulated via multiple bases)
    bases = ["https://api.binance.com", "https://api1.binance.com", "https://api-gcp.binance.com"]
    symbol = ASSET_SYMBOLS.get(asset, "BTCUSDT")
    
    for base in bases:
        url = f"{base}/api/v3/klines?symbol={symbol}&interval=1m&limit={lookback}"
        result = _api_request(url)
        if result and not isinstance(result, dict):
            try:
                price_then = float(result[0][1])
                price_now = float(result[-1][4])
                momentum_pct = ((price_now - price_then) / price_then) * 100
                return {"momentum_pct": momentum_pct, "price_now": price_now, "direction": "up" if momentum_pct > 0 else "down"}
            except: continue
            
    # Fallback to current price only (0 momentum)
    price = get_coingecko_price(asset)
    if price:
        return {"momentum_pct": 0.0, "price_now": price, "direction": "neutral"}
    return None

def discover_markets(asset="BTC", window="5m"):
    patterns = ASSET_PATTERNS.get(asset, ["bitcoin up or down"])
    url = "https://gamma-api.polymarket.com/markets?limit=20&closed=false&tag=crypto&order=createdAt&ascending=false"
    result = _api_request(url)
    if not result or "error" in result: return []
    
    found = []
    for m in result:
        q = (m.get("question") or "").lower()
        slug = m.get("slug", "")
        if any(p in q for p in patterns) and f"-{window}-" in slug:
            found.append(m)
    return found

# =============================================================================
# Execution
# =============================================================================
def run_cycle(dry_run=True):
    print(f"\n--- Albert FastLoop Cycle [{datetime.now().strftime('%H:%M:%S')}] ---")
    print(f"Target: {ASSET} {WINDOW} | Req: {MIN_MOMENTUM_PCT}% | Mode: {'DRY' if dry_run else 'LIVE'}")
    
    mom = get_momentum(ASSET)
    if not mom:
        print("❌ Failed to get market data.")
        return
    
    print(f"Price: ${mom['price_now']:,.2f} | Momentum: {mom['momentum_pct']:+.3f}%")
    
    if abs(mom['momentum_pct']) < MIN_MOMENTUM_PCT:
        print("⏸️ Waiting for stronger momentum...")
        return

    markets = discover_markets(ASSET, WINDOW)
    if not markets:
        print("⏸️ No active sprint markets found.")
        return

    best_m = markets[0]
    print(f"🎯 Target: {best_m['question']}")
    side = "yes" if mom['direction'] == "up" else "no"
    
    if dry_run:
        print(f"🧪 [DRY RUN] Would buy {side.upper()} for ${MAX_POSITION}")
    else:
        client = get_client()
        if not client: return
        
        print(f"🔴 [LIVE] Executing {side.upper()} trade...")
        try:
            # 1. Import market to Simmer
            import_res = client.import_market(f"https://polymarket.com/event/{best_m['slug']}")
            market_id = import_res.get("market_id")
            
            if not market_id:
                print(f"❌ Import failed: {import_res.get('error')}")
                return
                
            # 2. Execute Trade
            result = client.trade(market_id=market_id, side=side, amount=MAX_POSITION, source=TRADE_SOURCE)
            if result.success:
                print(f"✅ SUCCESS! Bought {result.shares_bought:.1f} shares. Trade ID: {result.trade_id}")
            else:
                print(f"❌ Trade failed: {result.error}")
        except Exception as e:
            print(f"❌ SDK Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    
    # Check client on startup if live
    if args.live:
        if not get_client():
            sys.exit(1)
        print("💪 Simmer SDK Connected. Live Execution Ready.")

    while True:
        try:
            run_cycle(dry_run=not args.live)
            time.sleep(30)
        except KeyboardInterrupt:
            break
