import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="IA Salarial USM", layout="wide")

def procesar_con_ia(texto):
    """
    Simula un motor de IA que analiza el contexto semántico del documento 
    para extraer valores incluso si el PDF está desordenado.
    """
    datos = {"Mes": "Desconocido", "Base": 0.0, "Bono": 0.0, "Liquido": 0.0}
    
    # 1. Identificación de Periodo (IA Semántica)
    meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
             "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    for m in meses:
        if re.search(m, texto, re.IGNORECASE):
            anio = re.search(r"202\d", texto)
            datos["Mes"] = f"{m} {anio.group(0) if anio else ''}"
            break

    # 2. Extracción de Valores Numéricos (Limpieza Pro)
    lineas = texto.split('\n')
    
    for linea in lineas:
        l_upper = linea.upper()
        # Buscar Sueldo Base
        if "BASE" in l_upper and any(c.isdigit() for c in linea):
            montos = re.findall(r'(\d[\d\.\,]+)', linea)
            if montos: datos["Base"] = limpiar_monto(montos[-1])
        
        # Buscar Bonos (Suma todos los conceptos de bonificación detectados)
        if any(keyword in l_upper for keyword in ["BONO", "BONIF", "ASIG", "USM"]) and "BASE" not in l_upper:
            montos = re.findall(r'(\d[\d\.\,]+)', linea)
            if montos: datos["Bono"] += limpiar_monto(montos[-1])
            
        # Buscar Líquido (El objetivo final)
        if any(keyword in l_upper for keyword in ["PAGAR", "LIQUIDO", "PERCIBIR", "DEPOSITAR"]):
            montos = re.findall(r'(\d[\d\.\,]+)', linea)
            if montos: datos["Liquido"] = limpiar_monto(montos[-1])

    return datos

def limpiar_monto(t):
    if not t: return 0.0
    t = re.sub(r'[^\d,.]', '', t)
    if t.count('.') > 1: t = t.replace('.', '')
    if ',' in t: t = t.replace('.', '').replace(',', '.')
    try: return float(t)
    except: return 0.0

# --- INTERFAZ ---
st.title("🤖 IA de Análisis Salarial USM")
st.markdown("Carga tus liquidaciones y la IA identificará automáticamente los montos.")

if 'historial' not in st.session_state:
    st.session_state.historial = []

with st.sidebar:
    st.header("📥 Entrada de Datos")
    archivos = st.file_uploader("Subir PDFs", type="pdf", accept_multiple_files=True)
    if st.button("Analizar con IA"):
        if archivos:
            for arc in archivos:
                with pdfplumber.open(arc) as pdf:
                    texto_pdf = "\n".join([p.extract_text() for p in pdf.pages])
                resultado = procesar_con_ia(texto_pdf)
                # Evitar duplicados
                st.session_state.historial = [h for h in st.session_state.historial if h["Mes"] != resultado["Mes"]]
                st.session_state.historial.append(resultado)
            st.success("Análisis completado")

if st.session_state.historial:
    df = pd.DataFrame(st.session_state.historial)
    df["Bruto"] = df["Base"] + df["Bono"]
    HORAS = 190.6
    
    # --- MÉTRICAS ---
    ultimo = df.iloc[-1]
    st.subheader(f"📍 Análisis detectado: {ultimo['Mes']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Líquido Final", f"$ {ultimo['Liquido']:,.0f}")
    c2.metric("Bruto Total", f"$ {ultimo['Bruto']:,.0f}")
    c3.metric("Valor Hora Liq.", f"$ {(ultimo['Liquido']/HORAS):,.0f}")
    c4.metric("Valor Hora Bruto", f"$ {(ultimo['Bruto']/HORAS):,.0f}")

    # --- GRÁFICOS ---
    st.divider()
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.subheader("📈 Evolución Temporal")
        fig_line = px.line(df, x="Mes", y=["Bruto", "Liquido"], markers=True, 
                           color_discrete_sequence=["#1f77b4", "#2ca02c"])
        st.plotly_chart(fig_line, use_container_width=True)
        
    with col_b:
        st.subheader("⚖️ Composición del Sueldo")
        df_pie = pd.DataFrame({
            "Tipo": ["Sueldo Base", "Bonos/Asig"],
            "Monto": [ultimo["Base"], ultimo["Bono"]]
        })
        fig_pie = px.pie(df_pie, values="Monto", names="Tipo", hole=0.5)
        st.plotly_chart(fig_pie, use_container_width=True)

    # --- TABLA ---
    st.subheader("📋 Historial Procesado")
    st.dataframe(df.style.format({"Base": "$ {:,.0f}", "Bono": "$ {:,.0f}", "Liquido": "$ {:,.0f}", "Bruto": "$ {:,.0f}"}), use_container_width=True)

else:
    st.warning("Aún no hay datos. Por favor, carga tus liquidaciones en la barra lateral.")
