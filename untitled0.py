import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import pdfplumber
import re

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Gestor Salarial USM", layout="wide")

# Estilo para mejorar la visualización de métricas
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 28px; color: #1f77b4; }
    .main { background-color: #fafafa; }
    </style>
    """, unsafe_allow_html=True)

def limpiar_monto(texto):
    if not texto: return 0.0
    limpio = re.sub(r"[^\d,]", "", texto).replace(",", ".")
    try:
        return float(limpio)
    except:
        return 0.0

# --- LÓGICA DE EXTRACCIÓN ---
def extraer_datos_pdf(file):
    datos = {"base": 0, "asig_fijas": 0, "bono": 0, "isapre_uf": 6.32}
    asig_keys = ["ANTIGUEDAD", "TITULO", "NIVEL", "PROFESIONALES"]
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            lineas = page.extract_text().split('\n')
            for linea in lineas:
                if "SUELDO BASE" in linea:
                    datos["base"] = limpiar_monto(linea.split("BASE")[-1])
                for key in asig_keys:
                    if key in linea:
                        datos["asig_fijas"] += limpiar_monto(linea.split("$")[-1] if "$" in linea else linea)
                if "BONIFICACION USM" in linea:
                    datos["bono"] = limpiar_monto(linea.split("USM")[-1])
                if "ISAPRE" in linea and "UF" in linea:
                    match = re.search(r"([\d,.]+)\s?UF", linea)
                    if match: datos["isapre_uf"] = limpiar_monto(match.group(1))
    return datos

@st.cache_data(ttl=3600)
def get_indicadores():
    try:
        data = requests.get("https://mindicador.cl/api").json()
        return data['uf']['valor'], data['utm']['valor']
    except: return 38500.0, 67500.0

uf_hoy, utm_hoy = get_indicadores()

# --- INTERFAZ ---
st.title("📈 Dashboard Salarial USM")

if 'datos' not in st.session_state:
    st.session_state.datos = {"base": 2409363, "asig_fijas": 228033, "bono": 0, "isapre_uf": 6.32}

with st.expander("📂 Cargar Liquidación PDF para actualizar valores", expanded=False):
    archivo = st.file_uploader("Sube tu PDF aquí", type="pdf")
    if archivo:
        extracted = extraer_datos_pdf(archivo)
        st.session_state.datos.update(extracted)
        st.success("✅ Datos extraídos")

# Inputs en Sidebar
with st.sidebar:
    st.header("Configuración de Montos")
    base = st.number_input("Sueldo Base", value=float(st.session_state.datos["base"]), step=1000.0)
    asig = st.number_input("Asignaciones Fijas", value=float(st.session_state.datos["asig_fijas"]), step=1000.0)
    bono = st.number_input("Bono USM", value=float(st.session_state.datos["bono"]), step=1000.0)
    plan_uf = st.number_input("Plan Isapre (UF)", value=float(st.session_state.datos["isapre_uf"]), step=0.01)
    apv = st.number_input("APV (Régimen B)", value=0.0, step=5000.0)

# --- CÁLCULOS ---
imponible = base + asig + bono
tope_afp = 84.3 * uf_hoy
base_prov = min(imponible, tope_afp)
desc_afp = base_prov * 0.1127
desc_cesantia = imponible * 0.006
salud_7 = base_prov * 0.07
salud_total = max(salud_7, plan_uf * uf_hoy)

base_tributable = imponible - desc_afp - salud_7 - desc_cesantia - apv
base_utm = base_tributable / utm_hoy
if base_utm <= 13.5: f, r = 0, 0
elif base_utm <= 30: f, r = 0.04, 0.54
elif base_utm <= 50: f, r = 0.08, 1.74
else: f, r = 0.135, 4.49

impuesto = max(0, (base_tributable * f) - (r * utm_hoy))
anticipo = bono * 0.8583 if bono > 0 else 0
liquido = (imponible + 3810) - (desc_afp + salud_total + desc_cesantia + impuesto + apv + anticipo)

# --- DESPLIEGUE DE MÉTRICAS ---
m1, m2, m3 = st.columns(3)
m1.metric("SUELDO BRUTO", f"$ {imponible:,.0f}")
m2.metric("SUELDO LÍQUIDO", f"$ {liquido:,.0f}")
m3.metric("RETENCIÓN IMPUESTOS", f"$ {impuesto:,.0f}")

st.divider()

# --- NUEVA SECCIÓN: GRÁFICOS COMPARATIVOS ---
st.subheader("📊 Comparativa Mensual")
col_graf1, col_graf2 = st.columns(2)

with col_graf1:
    # Gráfico Sueldo Bruto
    fig_bruto = px.bar(
        x=["Sueldo Bruto"], 
        y=[imponible],
        labels={'x': '', 'y': 'Monto ($)'},
        title="Sueldo Bruto Mensual",
        color_discrete_sequence=['#3366CC']
    )
    fig_bruto.update_layout(yaxis_range=[0, imponible * 1.2]) # Espacio arriba para mejor vista
    st.plotly_chart(fig_bruto, use_container_width=True)

with col_graf2:
    # Gráfico Sueldo Líquido
    fig_liquido = px.bar(
        x=["Sueldo Líquido"], 
        y=[liquido],
        labels={'x': '', 'y': 'Monto ($)'},
        title="Sueldo Líquido Mensual",
        color_discrete_sequence=['#109618']
    )
    fig_liquido.update_layout(yaxis_range=[0, imponible * 1.2]) # Misma escala para comparar visualmente
    st.plotly_chart(fig_liquido, use_container_width=True)

st.divider()

# --- DISTRIBUCIÓN DETALLADA ---
st.subheader("🎯 ¿Dónde se va tu dinero?")
df_pie = pd.DataFrame({
    "Item": ["Líquido", "AFP", "Salud", "Impuesto", "Ahorro/Otros"],
    "Monto": [liquido, desc_afp, salud_total, impuesto, apv + anticipo]
})
fig_pie = px.pie(df_pie, values="Monto", names="Item", hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
st.plotly_chart(fig_pie, use_container_width=True)

st.caption(f"Cálculos usando UF: ${uf_hoy:,.2f} | UTM: ${utm_hoy:,.0f}")
