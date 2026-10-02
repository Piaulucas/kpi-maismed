import streamlit as st

from ui import render_dashboard_mensal

st.set_page_config(page_title="KPI Mensal — Sert + Falcon + Mais Med", page_icon="🚑", layout="wide")

render_dashboard_mensal("🚑 KPI Mensal — Sert Med · Falcon · Mais Med", ['sert', 'maismed', 'falcon'])
