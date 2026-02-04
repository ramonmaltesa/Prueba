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
    # Quitamos todo lo que no sea número, punto o coma
    limpio = re.sub(r"[^\d,.]", "", texto)
    
    # Lógica para formato chileno: 1.234.567 o 1.234.567,00
    if limpio.count('.') >= 1 and "," in limpio: # Formato 1.234,56
        limpio = limpio.replace(".", "").replace(",", ".")
    elif limpio.count('.') >= 1: # Formato 1.234.567
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
    
    # --- BUSCADOR DE MES ---
    meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    periodo = "Desconocido"
    for m in meses:
        if m.upper() in texto_completo.upper():
            anio_match = re.search(r"202\d", texto_completo)
            periodo = f"{m} {anio_match.group(0) if anio_match else ''}"
            break

    # --- BUSCADORES MEJORADOS ---
    # Sueldo Base: Busca 'SUELDO BASE' y toma el primer número que aparezca después
    base_match = re.search(r"SUELDO\s+BASE.*?(\d[\d.,]*)", texto_completo, re.IGNORECASE)
    
    # BONO: Busca 'BONO' o 'BONIF' y captura el monto. 
    # Si hay varios, intentamos capturar el que parece ser el bono USM
    bono_match = re.search(r"(BONO|BONIF).*?USM.*?(\d[\d.,]*)", texto_completo, re.IGNORECASE)
    if not bono_match:
        # Intento genérico de bono si el específico falla
        bono_match = re.search(r"(BONIFICACION|BONO).*?(\d[\d.,]*)", texto_completo, re.IGNORECASE)
    
    # LÍQUIDO: Busca el monto después de palabras clave de cierre
    liq_match = re.search(r"(TOTAL\s+A\s+PAGAR|ALCANCE\s+L[IÍ]QUIDO|PAGAR|DEPOSITAR).*?(\d[\d.,]*)", texto_completo, re.IGNORECASE)

    return {
        "Mes": periodo,
        "Bruto Base": limpiar_monto(base_match.group(1)) if base_match else 0.0,
        "Bono USM": limpiar_monto(bono_match.group(2)) if bono_match else 0.0,
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
st.title("📈 Dashboard de Sueldos USM")

with st.sidebar:
    st.header("📂 Carga de Liquidaciones")
    archivos = st.file_uploader("Sube tus PDFs", type="pdf", accept_multiple_files=True)
    if st.button("Procesar"):
        if archivos:
            for arc in archivos:
                datos = extraer_datos_pdf(arc)
                # Reemplazar si el mes ya existe
                st.session_state.historial = [h for h in st.session_state.historial if h["Mes"] != datos["Mes"]]
                st.session_state.historial.append(datos)
            st.success("¡Procesado!")
    
    if st.button("🗑️ Limpiar Todo"):
        st.session_state.historial = []
        st.rerun()

if not st.session_state.historial:
    st.info("Sube tus archivos en la barra lateral.")
else:
    df_hist = pd.DataFrame(st.session_state.historial)
    # Importante: El Total Bruto es la suma del Base + Bono
    df_hist["Total Bruto"] = df_hist["Bruto Base"] + df_hist["Bono USM"]
    HORAS_MES = 190.6

    # --- MÉTRICAS ---
    ultimo = df_hist.iloc[-1]
    st.subheader(f"📊 Resultados de {ultimo['Mes']}")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Líquido", f"$ {ultimo['Líquido']:,.0f}")
    c2.metric("Bono Detectado", f"$ {ultimo['Bono USM']:,.0f}")
    c3.metric("V. Hora Líquido", f"$ {(ultimo['Líquido']/HORAS_MES):,.0f}")
    c4.metric("V. Hora Bruto", f"$ {(ultimo['Total Bruto']/HORAS_MES):,.0f}")

    # --- GRÁFICOS ---
    st.divider()
    # Gráfico de evolución
    fig_evol = px.line(df_hist, x="Mes", y=["Total Bruto", "Líquido"], markers=True, title="Evolución Mensual")
    st.plotly_chart(fig_evol, use_container_width=True)

    # Gráfico de Barras para el Bono
    st.subheader("💰 Detalle de Bonificaciones por Mes")
    fig_bono = px.bar(df_hist, x="Mes", y="Bono USM", text_auto='.3s', title="Monto de Bonos ($)", color_discrete_sequence=["#FFA500"])
    st.plotly_chart(fig_bono, use_container_width=True)

    # --- TABLA ---
    st.divider()
    st.dataframe(df_hist.style.format({"Bruto Base": "$ {:,.0f}", "Bono USM": "$ {:,.0f}", "Líquido": "$ {:,.0f}", "Total Bruto": "$ {:,.0f}"}), use_container_width=True)
