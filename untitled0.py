import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import pdfplumber
import re

# --- CONFIGURACIÓN ESTÉTICA ---
st.set_page_config(page_title="Gestor Salarial USM", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- LÓGICA DE EXTRACCIÓN DE PDF ---
def extraer_datos_pdf(file):
    with pdfplumber.open(file) as pdf:
        texto = pdf.pages[0].extract_text()
        
    # Buscamos patrones comunes en tus liquidaciones USM
    datos = {
        "base": re.search(r"SUELDO BASE \$?\s?([\d.]+)", texto),
        "bono": re.search(r"BONIFICACION USM \$?\s?([\d.]+)", texto),
        "afp_tasa": re.search(r"AFP\s?\(?([\d,]+)%\)?", texto)
    }
    
    # Limpieza de datos encontrados
    res = {}
    for k, v in datos.items():
        if v:
            val = v.group(1).replace(".", "").replace(",", ".")
            res[k] = float(val)
    return res

# --- OBTENER INDICADORES ---
@st.cache_data(ttl=3600)
def get_indicadores():
    try:
        data = requests.get("https://mindicador.cl/api").json()
        return data['uf']['valor'], data['utm']['valor']
    except: return 38500.0, 67000.0

uf_hoy, utm_hoy = get_indicadores()

# --- INTERFAZ PRINCIPAL ---
st.title("🚀 Dashboard de Gestión Salarial")

tabs = st.tabs(["📊 Calculadora & Análisis", "📂 Carga de Liquidaciones", "💡 Optimización Fiscal"])

with tabs[1]:
    st.header("Cargar nueva liquidación")
    uploaded_file = st.file_uploader("Arrastra tu PDF de la USM aquí", type="pdf")
    if uploaded_file:
        datos_extraidos = extraer_datos_pdf(uploaded_file)
        st.success("¡Datos extraídos con éxito!")
        st.json(datos_extraidos)
        st.info("Ahora puedes volver a la pestaña de 'Análisis' para ver los cálculos.")

with tabs[0]:
    with st.sidebar:
        st.header("Entradas Manuales")
        # Si se cargó un PDF, usamos esos valores, si no, los de por defecto
        val_base = datos_extraidos.get("base", 2409363.0) if uploaded_file else 2409363.0
        val_bono = datos_extraidos.get("bono", 0.0) if uploaded_file else 0.0
        
        base = st.number_input("Sueldo Base", value=float(val_base))
        bono = st.number_input("Bono USM", value=float(val_bono))
        apv = st.number_input("APV (Régimen B)", value=0.0)
        isapre_uf = st.number_input("Plan Isapre (UF)", value=6.32)

    # --- CÁLCULOS (Lógica optimizada) ---
    imponible = base + 228033 + bono  # Sueldo base + Asig. Fijas
    tope_afp = 84.3 * uf_hoy
    monto_afp = min(imponible, tope_afp) * 0.1127
    salud_7 = min(imponible, tope_afp) * 0.07
    salud_total = max(salud_7, isapre_uf * uf_hoy)
    
    # Impuesto
    base_tributable = imponible - monto_afp - salud_7 - (imponible * 0.006) - apv
    factor = 0.04 if (base_tributable/utm_hoy) > 13.5 else 0
    rebaja = 0.54 * utm_hoy if factor > 0 else 0
    impuesto = max(0, (base_tributable * factor) - rebaja)
    
    anticipo = bono * 0.8583 if bono > 0 else 0
    liquido = imponible + 3810 - (monto_afp + salud_total + (imponible * 0.006) + impuesto + apv + anticipo)

    # --- MÉTRICAS VISUALES ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Líquido Estimado", f"${liquido:,.0f}")
    m2.metric("Impuesto Único", f"${impuesto:,.0f}", delta=f"{factor*100}%", delta_color="inverse")
    m3.metric("Costo Isapre", f"${salud_total:,.0f}")
    m4.metric("Valor Hora", f"${(liquido/190.6):,.0f}")

    # --- GRÁFICOS ---
    st.divider()
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        df_plot = pd.DataFrame({
            "Categoría": ["Neto", "AFP", "Salud", "Impuesto", "Ahorro/Otros"],
            "Monto": [liquido, monto_afp, salud_total, impuesto, apv + anticipo]
        })
        fig = px.bar(df_plot, x="Categoría", y="Monto", color="Categoría", title="Desglose de Costos Mensuales")
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        fig_pie = px.pie(df_plot, values="Monto", names="Categoría", hole=0.5)
        st.plotly_chart(fig_pie, use_container_width=True)

with tabs[2]:
    st.header("Estrategia Fiscal")
    st.write("Si aumentas tu APV, puedes bajar de tramo de impuestos.")
    nuevo_apv = st.slider("Simular APV mensual", 0, 500000, int(apv))
    # Aquí podrías añadir una lógica que compare el impuesto actual vs el proyectado
