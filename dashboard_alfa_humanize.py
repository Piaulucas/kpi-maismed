import streamlit as st

from ui import render_dashboard_mensal

st.set_page_config(page_title="KPI Mensal — Alfa + Humanize", page_icon="🏥", layout="wide")

render_dashboard_mensal("🏥 KPI Mensal — Alfa Saúde · Humanize Life Care", ['humanize', 'alfa'])
