import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import pdfplumber
import re

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Dashboard Salarial USM PRO", layout="wide")

# --- FUNCIONES DE APOYO ---
def limpiar_monto(texto):
    if not texto: return 0.0
    limpio = re.sub(r"[^\d,]", "", texto).replace(",", ".")
    try: return float(limpio)
    except: return 0.0

def extraer_datos_pdf(file):
    texto_completo = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto_completo += page.extract_text() + "\n"
    
    periodo = re.search(r"Liquidación de sueldo\s+([A-Za-z]+\s+\d{4})", texto_completo)
    base = re.search(r"SUELDO BASE\s+\$?\s?([\d.]+)", texto_completo)
    bono = re.search(r"BONIFICACION USM\s+\$?\s?([\d.]+)", texto_completo)
    liquido = re.search(r"TOTAL A PAGAR\s+\$?\s?([\d.]+)", texto_completo)
    
    return {
        "Mes": periodo.group(1) if periodo else "Desconocido",
        "Bruto Base": limpiar_monto(base.group(1)) if base else 0.0,
        "Bono USM": limpiar_monto(bono.group(1)) if bono else 0.0,
        "Líquido": limpiar_monto(liquido.group(1)) if liquido else 0.0
    }

@st.cache_data(ttl=3600)
def get_indicadores():
    try:
        data = requests.get("https://mindicador.cl/api").json()
        return data['uf']['valor'], data['utm']['valor']
    except: return 38500.0, 67000.0

uf_hoy, utm_hoy = get_indicadores()

# --- BASE DE DATOS TEMPORAL ---
if 'historial' not in st.session_state:
    st.session_state.historial = []

# --- INTERFAZ ---
st.title("📈 Sistema de Gestión Salarial USM")

# 1. CARGA DE ARCHIVOS
with st.sidebar:
    st.header("Cargar Liquidaciones")
    archivos = st.file_uploader("Sube tus PDFs", type="pdf", accept_multiple_files=True)
    if st.button("Procesar Archivos"):
        if archivos:
            for arc in archivos:
                datos = extraer_datos_pdf(arc)
                if datos["Mes"] not in [x["Mes"] for x in st.session_state.historial]:
                    st.session_state.historial.append(datos)
            st.success("Historial actualizado")

# Validar si hay datos para mostrar
if not st.session_state.historial:
    st.warning("👈 Por favor, carga tus liquidaciones en el panel de la izquierda para ver los gráficos.")
else:
    df_hist = pd.DataFrame(st.session_state.historial)
    df_hist["Total Bruto"] = df_hist["Bruto Base"] + df_hist["Bono USM"]

    # --- SECCIÓN 1: EVOLUCIÓN HISTÓRICA (NUEVO) ---
    st.header("📅 Evolución Histórica")
    
    # Gráfico de líneas (Bruto vs Líquido por Mes)
    fig_lineas = px.line(df_hist, x="Mes", y=["Total Bruto", "Líquido"], 
                         markers=True, title="Evolución de Ingresos Mensuales",
                         color_discrete_map={"Total Bruto": "#3366CC", "Líquido": "#109618"})
    st.plotly_chart(fig_lineas, use_container_width=True)

    # Detalle en Tabla
    with st.expander("Ver detalle de la tabla"):
        st.table(df_hist.style.format({"Bruto Base": "$ {:,.0f}", "Bono USM": "$ {:,.0f}", "Líquido": "$ {:,.0f}", "Total Bruto": "$ {:,.0f}"}))

    st.divider()

    # --- SECCIÓN 2: GRÁFICOS DE COMPARACIÓN (PEDIDOS ANTERIORMENTE) ---
    st.header("📊 Comparativa de Último Mes")
    ultimo_mes = df_hist.iloc[-1]
    
    col_bar1, col_bar2 = st.columns(2)
    with col_bar1:
        fig_bruto = px.bar(x=["Sueldo Bruto Total"], y=[ultimo_mes["Total Bruto"]], 
                           title=f"Bruto en {ultimo_mes['Mes']}", color_discrete_sequence=['#3366CC'])
        st.plotly_chart(fig_bruto, use_container_width=True)
        
    with col_bar2:
        fig_liq = px.bar(x=["Sueldo Líquido"], y=[ultimo_mes["Líquido"]], 
                         title=f"Líquido en {ultimo_mes['Mes']}", color_discrete_sequence=['#109618'])
        st.plotly_chart(fig_liq, use_container_width=True)

    st.divider()

    # --- SECCIÓN 3: DESGLOSE DE COSTOS (PEDIDO ANTERIORMENTE) ---
    st.header("🎯 Desglose de Retenciones y Ahorro")
    
    # Simulación de descuentos para el gráfico de torta basado en el último mes
    bruto_u = ultimo_mes["Total Bruto"]
    liq_u = ultimo_mes["Líquido"]
    # Estimación de descuentos legales para visualización
    df_torta = pd.DataFrame({
        "Concepto": ["Sueldo Líquido", "Impuestos y Leyes Sociales"],
        "Monto": [liq_u, bruto
