import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import pdfplumber
import re

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Dashboard Salarial USM PRO", layout="wide")

def limpiar_monto(texto):
    if not texto: return 0.0
    # Limpieza profunda: solo números y el separador decimal
    limpio = re.sub(r"[^\d,.]", "", texto)
    if "." in limpio and "," in limpio: # Formato 1.234,56
        limpio = limpio.replace(".", "").replace(",", ".")
    elif limpio.count(".") > 1: # Formato 1.234.567
        limpio = limpio.replace(".", "")
    elif "," in limpio: # Formato 1234,56
        limpio = limpio.replace(",", ".")
    try:
        return float(limpio)
    except:
        return 0.0

def extraer_datos_pdf(file):
    texto_completo = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto_completo += page.extract_text() + "\n"
    
    # 1. Búsqueda de Mes
    meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    periodo = "Desconocido"
    for m in meses:
        if m.upper() in texto_completo.upper():
            anio = re.search(r"202\d", texto_completo)
            periodo = f"{m} {anio.group(0) if anio else ''}"
            break

    # 2. Búsqueda de Sueldo Base (Primer número tras 'SUELDO BASE')
    base_match = re.search(r"SUELDO\s+BASE.*?(\d[\d\.,]*)", texto_completo, re.IGNORECASE)
    val_base = limpiar_monto(base_match.group(1)) if base_match else 0.0

    # 3. Búsqueda de Bono (Busca 'BONIF', 'BONO' o 'USM' que NO sea el sueldo base)
    # Intentamos capturar montos que estén asociados a palabras de bonificación
    bono_pattern = r"(?:BONO|BONIF|ASIG\.)\s+.*?(\d[\d\.,]*)"
    bonos_encontrados = re.findall(bono_pattern, texto_completo, re.IGNORECASE)
    
    # Si encontramos varios, sumamos los que sean significativos (> 10.000)
    val_bono = sum([limpiar_monto(b) for b in bonos_encontrados])
    
    # 4. Búsqueda de Líquido
    liq_match = re.search(r"(TOTAL\s+A\s+PAGAR|ALCANCE\s+L[IÍ]QUIDO|LIQUIDO\s+A\s+PERCIBIR).*?(\d[\d\.,]*)", texto_completo, re.IGNORECASE | re.DOTALL)
    val_liq = limpiar_monto(liq_match.group(2)) if liq_match else 0.0

    return {
        "Mes": periodo,
        "Bruto Base": val_base,
        "Bono USM": val_bono,
        "Líquido": val_liq
    }

@st.cache_data(ttl=3600)
def get_indicadores():
    try:
        data = requests.get("https://mindicador.cl/api").json()
        return data['uf']['valor'], data['utm']['valor']
    except: return 38500.0, 67000.0

uf_hoy, utm_hoy = get_indicadores()

if 'historial' not in st.session_state:
    st.session_state.historial = []

# --- INTERFAZ ---
st.title("🏦 Sistema de Gestión Salarial USM")

with st.sidebar:
    st.header("📂 Carga de Liquidaciones")
    archivos = st.file_uploader("Sube tus PDFs", type="pdf", accept_multiple_files=True)
    if st.button("Procesar Archivos"):
        if archivos:
            for arc in archivos:
                datos = extraer_datos_pdf(arc)
                st.session_state.historial = [h for h in st.session_state.historial if h["Mes"] != datos["Mes"]]
                st.session_state.historial.append(datos)
            st.success("¡Historial actualizado!")
    
    if st.button("🗑️ Limpiar Todo"):
        st.session_state.historial = []
        st.rerun()

if not st.session_state.historial:
    st.info("💡 Sube tus liquidaciones PDF para generar los gráficos.")
else:
    df_hist = pd.DataFrame(st.session_state.historial)
    df_hist["Total Bruto"] = df_hist["Bruto Base"] + df_hist["Bono USM"]
    HORAS_MES = 190.6

    # --- MÉTRICAS ---
    ultimo = df_hist.iloc[-1]
    st.subheader(f"📊 Reporte de {ultimo['Mes']}")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sueldo Líquido", f"$ {ultimo['Líquido']:,.0f}")
    c2.metric("Sueldo Bruto Total", f"$ {ultimo['Total Bruto']:,.0f}")
    c3.metric("Valor Hora Líquido", f"$ {(ultimo['Líquido']/HORAS_MES):,.0f}")
    c4.metric("Valor Hora Bruto", f"$ {(ultimo['Total Bruto']/HORAS_MES):,.0f}")

    # --- GRÁFICOS ---
    st.divider()
    
    # 1. Evolución de Ingresos
    fig_evol = px.line(df_hist, x="Mes", y=["Total Bruto", "Líquido"], markers=True,
                       title="Evolución Bruto vs Líquido Mensual",
                       color_discrete_map={"Total Bruto": "#3366CC", "Líquido": "#109618"})
    st.plotly_chart(fig_evol, use_container_width=True)

    # 2. Desglose de Haberes (Último Mes)
    st.subheader(f"💰 Desglose de Haberes: {ultimo['Mes']}")
    df_haberes = pd.DataFrame({
        "Concepto": ["Sueldo Base", "Bonos/Asignaciones"],
        "Monto": [ultimo["Bruto Base"], ultimo["Bono USM"]]
    })
    fig_hab = px.bar(df_haberes, x="Concepto", y="Monto", color="Concepto", text_auto='.4s')
    st.plotly_chart(fig_hab, use_container_width=True)

    # --- TABLA CRONOLÓGICA ---
    st.divider()
    st.header("📋 Historial de Liquidaciones")
    df_hist_display = df_hist.copy()
    df_hist_display["V. Hora Líq"] = df_hist_display["Líquido"] / HORAS_MES
    
    st.dataframe(df_hist_display.style.format({
        "Bruto Base": "$ {:,.0f}", 
        "Bono USM": "$ {:,.0f}", 
        "Líquido": "$ {:,.0f}", 
        "Total Bruto": "$ {:,.0f}",
        "V. Hora Líq": "$ {:,.0f}"
    }), use_container_width=True)

st.caption(f"Indicadores hoy: UF ${uf_hoy} | UTM ${utm_hoy} | Jornada: 44 hrs/sem")
