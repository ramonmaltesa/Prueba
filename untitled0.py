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
    if st.button("Limpiar Historial"):
        st.session_state.historial = []
        st.rerun()

if not st.session_state.historial:
    st.warning("👈 Por favor, carga tus liquidaciones en el panel de la izquierda.")
else:
    df_hist = pd.DataFrame(st.session_state.historial)
    df_hist["Total Bruto"] = df_hist["Bruto Base"] + df_hist["Bono USM"]

    # --- MÉTRICAS GENERALES ---
    promedio_liq = df_hist["Líquido"].mean()
    ultimo_mes = df_hist.iloc[-1]
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Último Líquido", f"$ {ultimo_mes['Líquido']:,.0f}")
    c2.metric("Promedio Líquido Histórico", f"$ {promedio_liq:,.0f}")
    c3.metric("Total Meses Cargados", len(df_hist))

    st.divider()

    # --- SECCIÓN 1: EVOLUCIÓN HISTÓRICA ---
    st.header("📅 Evolución Histórica")
    fig_lineas = px.line(df_hist, x="Mes", y=["Total Bruto", "Líquido"], 
                         markers=True, title="Evolución Bruto vs Líquido",
                         color_discrete_map={"Total Bruto": "#3366CC", "Líquido": "#109618"})
    st.plotly_chart(fig_lineas, use_container_width=True)

    # --- SECCIÓN 2: GRÁFICOS DE COMPARACIÓN ÚLTIMO MES ---
    st.header(f"📊 Detalle de {ultimo_mes['Mes']}")
    col_bar1, col_bar2 = st.columns(2)
    
    with col_bar1:
        fig_bruto = px.bar(x=["Sueldo Bruto Total"], y=[ultimo_mes["Total Bruto"]], 
                           title="Comparación Bruto", color_discrete_sequence=['#3366CC'])
        st.plotly_chart(fig_bruto, use_container_width=True)
        
    with col_bar2:
        fig_liq = px.bar(x=["Sueldo Líquido"], y=[ultimo_mes["Líquido"]], 
                         title="Comparación Líquido", color_discrete_sequence=['#109618'])
        st.plotly_chart(fig_liq, use_container_width=True)

    # --- SECCIÓN 3: DESGLOSE DE COSTOS ---
    st.header("🎯 Eficiencia del Sueldo")
    # Calculamos la retención (lo que no llegó al líquido)
    retencion = ultimo_mes["Total Bruto"] - ultimo_mes["Líquido"]
    
    df_torta = pd.DataFrame({
        "Concepto": ["Sueldo Líquido", "Retenciones (Impuestos/Leyes/Anticipos)"],
        "Monto": [ultimo_mes["Líquido"], retencion]
    })
    
    fig_pie = px.pie(df_torta, values="Monto", names="Concepto", hole=0.5, 
                     color_discrete_sequence=["#109618", "#CC3333"])
    st.plotly_chart(fig_pie, use_container_width=True)

    # --- SECCIÓN 4: TABLA DE DATOS ---
    st.header("📋 Detalle Cronológico")
    st.dataframe(df_hist.style.format({
        "Bruto Base": "$ {:,.0f}", 
        "Bono USM": "$ {:,.0f}", 
        "Líquido": "$ {:,.0f}", 
        "Total Bruto": "$ {:,.0f}"
    }), use_container_width=True)

st.caption(f"Indicadores: UF ${uf_hoy:,.2f} | UTM ${utm_hoy:,.0f}")
