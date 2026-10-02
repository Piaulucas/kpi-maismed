import streamlit as st

from ui import EMPRESAS, render_dashboard_mensal

st.set_page_config(page_title="KPI Mensal — Todas as Empresas", page_icon="🏥", layout="wide")

render_dashboard_mensal("🏥 KPI Mensal — Todas as Empresas", list(EMPRESAS.keys()))
