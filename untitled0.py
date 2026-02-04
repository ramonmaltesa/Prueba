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
    # Elimina todo lo que no sea dígito o coma/punto
    limpio = re.sub(r"[^\d,]", "", texto)
    # Maneja el formato chileno (puntos para miles, coma para decimales o viceversa)
    if "," in limpio and "." in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    elif "," in limpio:
        limpio = limpio.replace(",", ".")
    return float(limpio) if limpio else 0.0

def extraer_datos_pdf(file):
    texto_completo = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto_completo += page.extract_text() + "\n"
    
    # --- BUSQUEDA CON EXPRESIONES REGULARES FLEXIBLES ---
    # Busca Mes y Año
    meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    periodo = "Desconocido"
    for m in meses:
        if m.upper() in texto_completo.upper():
            anio = re.search(r"202\d", texto_completo)
            periodo = f"{m} {anio.group(0) if anio else ''}"
            break

    # Busca Sueldo Base (ignora símbolos entre la palabra y el número)
    base_match = re.search(r"SUELDO BASE\s*[:$\s]*([\d\.]+)", texto_completo)
    # Busca Bono USM
    bono_match = re.search(r"BONIFICACION USM\s*[:$\s]*([\d\.]+)", texto_completo)
    # Busca Líquido (Busca el monto más grande al final de la liquidación o cerca de 'PAGAR')
    liq_match = re.search(r"(TOTAL A PAGAR|ALCANCE LIQUIDO|LIQUIDO A PERCIBIR)\s*[:$\s]*([\d\.]+)", texto_completo, re.IGNORECASE)

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
                # Solo agregar si el mes no existe o si queremos actualizarlo
                st.session_state.historial = [h for h in st.session_state.historial if h["Mes"] != datos["Mes"]]
                st.session_state.historial.append(datos)
            st.success("¡Datos procesados!")
    
    if st.button("🗑️ Borrar Todo"):
        st.session_state.historial = []
        st.rerun()

if not st.session_state.historial:
    st.info("💡 Sube tus liquidaciones en el panel lateral para comenzar el análisis.")
else:
    # Ordenar historial por mes (opcional, requiere lógica extra para meses cronológicos)
    df_hist = pd.DataFrame(st.session_state.historial)
    df_hist["Total Bruto"] = df_hist["Bruto Base"] + df_hist["Bono USM"]
    HORAS_MES = 190.6

    # --- MÉTRICAS ---
    ultimo = df_hist.iloc[-1]
    v_h_l = ultimo["Líquido"] / HORAS_MES
    v_h_b = ultimo["Total Bruto"] / HORAS_MES

    st.subheader(f"📍 Resumen: {ultimo['Mes']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sueldo Líquido", f"$ {ultimo['Líquido']:,.0f}")
    c2.metric("Sueldo Bruto", f"$ {ultimo['Total Bruto']:,.0f}")
    c3.metric("V. Hora Líquido", f"$ {v_h_l:,.0f}")
    c4.metric("V. Hora Bruto", f"$ {v_h_b:,.0f}")

    # --- GRÁFICOS ---
    st.divider()
    st.header("📊 Visualización de Datos")
    
    # 1. Evolución
    fig_lineas = px.line(df_hist, x="Mes", y=["Total Bruto", "Líquido"], markers=True,
                         title="Historial de Ingresos", template="plotly_white")
    st.plotly_chart(fig_lineas, use_container_width=True)

    # 2. Barras Comparativas
    col_a, col_b = st.columns(2)
    with col_a:
        st.plotly_chart(px.bar(df_hist, x="Mes", y="Total Bruto", title="Bruto por Mes"), use_container_width=True)
    with col_b:
        st.plotly_chart(px.bar(df_hist, x="Mes", y="Líquido", title="Líquido por Mes"), use_container_width=True)

    # --- TABLA ---
    st.divider()
    st.header("📋 Detalle de Registros")
    df_disp = df_hist.copy()
    df_disp["V. Hora Liq"] = df_disp["Líquido"] / HORAS_MES
    st.dataframe(df_disp.style.format({"Bruto Base": "$ {:,.0f}", "Bono USM": "$ {:,.0f}", "Líquido": "$ {:,.0f}", "Total Bruto": "$ {:,.0f}", "V. Hora Liq": "$ {:,.0f}"}), use_container_width=True)

st.caption(f"UF: ${uf_hoy} | UTM: ${utm_hoy}")
