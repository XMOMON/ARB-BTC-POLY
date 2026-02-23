import streamlit as st
import pandas as pd
import time
from datetime import datetime
import requests
import json

# Page Config
st.set_page_config(page_title="Albert FastLoop Dashboard", page_icon="🪙", layout="wide")

# Custom CSS for that "winning" vibe
st.markdown("""
    <style>
    .main { background-color: #0E1117; }
    .stMetric { background-color: #161B22; padding: 15px; border-radius: 10px; border: 1px solid #30363D; }
    .win-card { background-color: #1F6722; color: white; padding: 10px; border-radius: 5px; margin: 5px 0; }
    .wait-card { background-color: #21262D; color: #8B949E; padding: 10px; border-radius: 5px; margin: 5px 0; }
    </style>
    """, unsafe_allow_html=True)

st.title("🪙 Albert Polymarket FastLoop")
st.markdown("Monitoring BTC/ETH/SOL 5m & 15m Sprints")

# Sidebar Config
st.sidebar.header("Settings")
asset = st.sidebar.selectbox("Target Asset", ["BTC", "ETH", "SOL"])
window = st.sidebar.selectbox("Window", ["5m", "15m"])
momentum_req = st.sidebar.slider("Momentum Threshold (%)", 0.1, 2.0, 0.5)

# Layout
col1, col2, col3 = st.columns(3)

# Mock Data for UI Demo (In real use, this pulls from your fast_trader.py logs)
with col1:
    st.metric("Live Price (BTC)", "$64,582", "+0.02%")
with col2:
    st.metric("Momentum (5m)", "0.12%", delta_color="normal")
with col3:
    st.metric("Daily Profit", "$12.50", "+20%")

st.divider()

# Momentum Gauge Simulation
st.subheader("Momentum Analysis")
momentum_val = 0.12
st.progress(min(momentum_val / momentum_req, 1.0), text=f"Momentum Strength: {momentum_val}% / {momentum_req}%")

# Activity Log (Like the screenshot you showed)
st.subheader("Recent Activity")

# Example Wins
st.markdown("""
<div class="win-card">🟢 <b>WON</b> Bitcoin Up - Feb 24, 05:00-05:05 ET | +$0.50 (20%)</div>
<div class="win-card">🟢 <b>WON</b> Bitcoin Down - Feb 24, 04:45-05:00 ET | +$0.50 (20%)</div>
<div class="wait-card">⚪ <b>SCANNING</b> Searching for price divergence in {asset} {window}...</div>
""".format(asset=asset, window=window), unsafe_allow_html=True)

# Auto-refresh
time.sleep(5)
st.rerun()
