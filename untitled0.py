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
    # Eliminar todo lo que no sea número, punto o coma
    limpio = re.sub(r"[^\d,.]", "", texto)
    # Si tiene puntos y comas (formato 1.234,56), quitar puntos y cambiar coma por punto
    if "." in limpio and "," in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    # Si solo tiene coma (formato 1234,56), cambiar por punto
    elif "," in limpio:
        limpio = limpio.replace(",", ".")
    # Si tiene puntos como separadores de miles (formato 1.234.567), quitarlos
    elif limpio.count(".") > 1:
        limpio = limpio.replace(".", "")
    
    try:
        return float(limpio)
    except:
        return 0.0

def extraer_datos_pdf(file):
    texto_completo = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto_completo += page.extract_text() + "\n"
    
    # --- BUSCADOR DE MES ---
    meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    periodo = "Desconocido"
    for m in meses:
        if m.upper() in texto_completo.upper():
            anio_match = re.search(r"202\d", texto_completo)
            periodo = f"{m} {anio_match.group(0) if anio_match else ''}"
            break

    # --- BUSCADORES FLEXIBLES (Regex) ---
    # Busca 'SUELDO BASE' seguido de cualquier cosa hasta el número
    base_match = re.search(r"SUELDO\s+BASE.*?([\d.,]+)", texto_completo, re.IGNORECASE)
    # Busca 'BONIFICACION USM'
    bono_match = re.search(r"BONIFICACION\s+USM.*?([\d.,]+)", texto_completo, re.IGNORECASE)
    # Busca el valor líquido (Acepta 'TOTAL A PAGAR', 'ALCANCE LIQUIDO', 'PAGAR', etc.)
    liq_match = re.search(r"(TOTAL\s+A\s+PAGAR|ALCANCE\s+L[IÍ]QUIDO|LIQUIDO\s+A\s+PERCIBIR).*?([\d.,]+)", texto_completo, re.IGNORECASE | re.DOTALL)

    return {
        "Mes": periodo,
        "Bruto Base": limpiar_monto(base_match.group(1)) if base_match else 0.0,
        "Bono USM": limpiar_monto(bono_match.group(1)) if bono_match else 0.0,
        "Líquido": limpiar_monto(liq_match.group(2)) if liq_match else 0.0
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
st.title("📈 Sistema de Gestión Salarial USM")

with st.sidebar:
    st.header("📂 Carga de Documentos")
    archivos = st.file_uploader("Sube tus liquidaciones PDF", type="pdf", accept_multiple_files=True)
    if st.button("Procesar y Actualizar"):
        if archivos:
            for arc in archivos:
                datos = extraer_datos_pdf(arc)
                # Actualizar si existe, sino agregar
                st.session_state.historial = [h for h in st.session_state.historial if h["Mes"] != datos["Mes"]]
                st.session_state.historial.append(datos)
            st.success("¡Datos procesados!")
    
    if st.button("🗑️ Borrar Todo"):
        st.session_state.historial = []
        st.rerun()

if not st.session_state.historial:
    st.info("💡 Sube tus liquidaciones en el panel lateral para comenzar.")
else:
    df_hist = pd.DataFrame(st.session_state.historial)
    df_hist["Total Bruto"] = df_hist["Bruto Base"] + df_hist["Bono USM"]
    HORAS_MES = 190.6

    # --- MÉTRICAS ---
    ultimo = df_hist.iloc[-1]
    # Cálculos forzados
    liq_val = ultimo["Líquido"]
    bruto_val = ultimo["Total Bruto"]
    
    v_h_l = liq_val / HORAS_MES if liq_val > 0 else 0
    v_h_b = bruto_val / HORAS_MES if bruto_val > 0 else 0

    st.subheader(f"📍 Resumen Detectado: {ultimo['Mes']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sueldo Líquido", f"$ {liq_val:,.0f}")
    c2.metric("Sueldo Bruto", f"$ {bruto_val:,.0f}")
    c3.metric("V. Hora Líquido", f"$ {v_h_l:,.0f}")
    c4.metric("V. Hora Bruto", f"$ {v_h_b:,.0f}")

    # --- GRÁFICOS ---
    st.divider()
    
    # 1. Evolución Histórica
    fig_evol = px.line(df_hist, x="Mes", y=["Total Bruto", "Líquido"], markers=True,
                       title="Evolución Bruto vs Líquido", color_discrete_sequence=["#3366CC", "#109618"])
    st.plotly_chart(fig_evol, use_container_width=True)

    # 2. Barras de Valor Hora
    st.subheader("⏱️ Valor Hora por Mes")
    df_hist["V. Hora Liq"] = df_hist["Líquido"] / HORAS_MES
    fig_bar = px.bar(df_hist, x="Mes", y="V. Hora Liq", text_auto='.0s',
                     title="Evolución Valor Hora Líquido ($)", color_discrete_sequence=["#109618"])
    st.plotly_chart(fig_bar, use_container_width=True)

    # --- TABLA DETALLADA ---
    st.divider()
    st.header("📋 Detalle de Registros")
    df_disp = df_hist.copy()
    df_disp["V. Hora Bruto"] = df_disp["Total Bruto"] / HORAS_MES
    df_disp["V. Hora Liq"] = df_disp["Líquido"] / HORAS_MES
    
    st.dataframe(df_disp.style.format({
        "Bruto Base": "$ {:,.0f}", 
        "Bono USM": "$ {:,.0f}", 
        "Líquido": "$ {:,.0f}", 
        "Total Bruto": "$ {:,.0f}", 
        "V. Hora Bruto": "$ {:,.0f}",
        "V. Hora Liq": "$ {:,.0f}"
    }), use_container_width=True)

st.caption(f"UF: ${uf_hoy} | UTM: ${utm_hoy} | Basado en 44 hrs semanales")
