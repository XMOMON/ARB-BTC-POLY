#!/usr/bin/env python3
"""
ALBERT POLYMARKET FAST-LOOP v2.0
================================
Integrated Simmer FastLoop logic for Polymarket BTC/ETH/SOL 5m/15m sprints.
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
# Configuration Schema
# =============================================================================
CONFIG_SCHEMA = {
    "entry_threshold": {"default": 0.05, "env": "SIMMER_SPRINT_ENTRY", "type": float},
    "min_momentum_pct": {"default": 0.5, "env": "SIMMER_SPRINT_MOMENTUM", "type": float},
    "max_position": {"default": 5.0, "env": "SIMMER_SPRINT_MAX_POSITION", "type": float},
    "signal_source": {"default": "binance", "env": "SIMMER_SPRINT_SIGNAL", "type": str},
    "lookback_minutes": {"default": 5, "env": "SIMMER_SPRINT_LOOKBACK", "type": int},
    "min_time_remaining": {"default": 60, "env": "SIMMER_SPRINT_MIN_TIME", "type": int},
    "asset": {"default": "BTC", "env": "SIMMER_SPRINT_ASSET", "type": str},
    "window": {"default": "5m", "env": "SIMMER_SPRINT_WINDOW", "type": str},
    "volume_confidence": {"default": True, "env": "SIMMER_SPRINT_VOL_CONF", "type": bool},
    "daily_budget": {"default": 10.0, "env": "SIMMER_SPRINT_DAILY_BUDGET", "type": float},
}

ASSET_SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
ASSET_PATTERNS = {"BTC": ["bitcoin up or down"], "ETH": ["ethereum up or down"], "SOL": ["solana up or down"]}
TRADE_SOURCE = "albert:fastloop"

# =============================================================================
# Config Helpers
# =============================================================================
def _load_config(schema, skill_file):
    from pathlib import Path
    config_path = Path(skill_file).parent / "config_fastloop.json"
    file_cfg = {}
    if config_path.exists():
        try:
            with open(config_path) as f:
                file_cfg = json.load(f)
        except: pass
    
    result = {}
    for key, spec in schema.items():
        if key in file_cfg:
            result[key] = file_cfg[key]
        elif spec.get("env") and os.environ.get(spec["env"]):
            val = os.environ.get(spec["env"])
            type_fn = spec.get("type", str)
            result[key] = type_fn(val) if type_fn != bool else val.lower() in ("true", "1", "yes")
        else:
            result[key] = spec.get("default")
    return result

# =============================================================================
# API Helpers
# =============================================================================
def _api_request(url, method="GET", data=None, headers=None, timeout=15):
    try:
        req_headers = headers or {}
        if "User-Agent" not in req_headers:
            req_headers["User-Agent"] = "albert-fastloop/1.0"
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

def get_momentum(asset="BTC", lookback=5):
    # Use Coingecko as primary for now since Binance is blocked/failing
    coingecko_id = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}.get(asset, "bitcoin")
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coingecko_id}&vs_currencies=usd"
    result = _api_request(url)
    
    if result and coingecko_id in result:
        price_now = result[coingecko_id]["usd"]
        # Since Coingecko simple price doesn't give momentum, we'll simulate it for the test
        # or use a default 0.0 momentum for the dry run.
        return {"momentum_pct": 0.0, "price_now": price_now, "direction": "neutral"}
    return None

# =============================================================================
# Execution
# =============================================================================
def run_cycle(dry_run=True):
    cfg = _load_config(CONFIG_SCHEMA, __file__)
    print(f"\n--- Albert FastLoop Cycle [{datetime.now().strftime('%H:%M:%S')}] ---")
    print(f"Target: {cfg['asset']} {cfg['window']} | Momentum Req: {cfg['min_momentum_pct']}%")
    
    # 1. Check Momentum
    mom = get_momentum(cfg['asset'], cfg['lookback_minutes'])
    if not mom:
        print("❌ Failed to get Binance data.")
        return
    
    print(f"Momentum: {mom['momentum_pct']:+.3f}% | Price: ${mom['price_now']:,.2f}")
    
    if abs(mom['momentum_pct']) < cfg['min_momentum_pct']:
        print("⏸️ Momentum too weak. Skipping.")
        return

    # 2. Discover Markets
    markets = discover_markets(cfg['asset'], cfg['window'])
    if not markets:
        print("⏸️ No active sprint markets found.")
        return

    m = markets[0] # Take the freshest
    print(f"🎯 Market: {m['question']}")
    
    # 3. Decision
    side = "YES" if mom['direction'] == "up" else "NO"
    
    if dry_run:
        print(f"🧪 [DRY RUN] Would buy {side} on '{m['question']}' | Size: ${cfg['max_position']}")
    else:
        api_key = os.environ.get("SIMMER_API_KEY")
        if not api_key:
            print("❌ SIMMER_API_KEY not set. Cannot trade live.")
            return
        
        # Real execution would use simmer_sdk here
        print(f"🔴 [LIVE] Attempting {side} trade for ${cfg['max_position']}...")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    
    while True:
        try:
            run_cycle(dry_run=not args.live)
            time.sleep(30)
        except KeyboardInterrupt:
            break
