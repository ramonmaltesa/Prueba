import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="IA Salarial USM - Dashboard Completo", layout="wide")

def limpiar_monto_robusto(t):
    if not t: return 0.0
    # Eliminar todo lo que no sea dígito o separadores
    limpio = re.sub(r'[^\d,.]', '', t)
    
    # Filtro anti-folios: Si el número es muy largo y no tiene separadores, es un ID
    solo_numeros = re.sub(r'[^\d]', '', limpio)
    if len(solo_numeros) > 8 and "." not in limpio and "," not in limpio:
        return 0.0

    # Normalizar formato decimal
    if "." in limpio and "," in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    elif limpio.count(".") > 1:
        limpio = limpio.replace(".", "")
    elif "," in limpio:
        limpio = limpio.replace(",", ".")
        
    try:
        val = float(limpio)
        return val if val < 15000000 else 0.0 # Límite de seguridad 15M
    except:
        return 0.0

def extractor_inteligente(texto):
    datos = {"Mes": "Desconocido", "Base": 0.0, "Bono": 0.0, "Liquido": 0.0}
    
    # 1. Identificar Mes
    meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
             "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    for m in meses:
        if m.upper() in texto.upper():
            anio = re.search(r"202\d", texto)
            datos["Mes"] = f"{m} {anio.group(0) if anio else ''}"
            break

    lineas = texto.split('\n')
    for linea in lineas:
        linea_u = linea.upper()
        numeros = re.findall(r'(\d[\d\.\,]+)', linea)
        if not numeros: continue
        
        # Lógica de asignación por contexto
        if "SUELDO BASE" in linea_u:
            datos["Base"] = limpiar_monto_robusto(numeros[-1])
        elif "ANTICIPO" in linea_u and "USM" in linea_u:
            # Captura el monto específico del anticipo
            datos["Bono"] = limpiar_monto_robusto(numeros[-1])
        elif any(k in linea_u for k in ["TOTAL A PAGAR", "ALCANCE LIQUIDO", "LIQUIDO A PERCIBIR"]):
            datos["Liquido"] = limpiar_monto_robusto(numeros[-1])

    return datos

# --- ESTADO DE SESIÓN ---
if 'historial' not in st.session_state:
    st.session_state.historial = []

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("📂 Carga de Datos")
    archivos = st.file_uploader("Subir Liquidaciones (PDF)", type="pdf", accept_multiple_files=True)
    if st.button("🚀 Procesar con IA"):
        if archivos:
            for arc in archivos:
                with pdfplumber.open(arc) as pdf:
                    texto = "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
                res = extractor_inteligente(texto)
                if res["Liquido"] > 0 or res["Base"] > 0:
                    # Evitar duplicados por mes
                    st.session_state.historial = [h for h in st.session_state.historial if h["Mes"] != res["Mes"]]
                    st.session_state.historial.append(res)
            st.success("Análisis completado")
    
    if st.button("🗑️ Reiniciar Todo"):
        st.session_state.historial = []
        st.rerun()

# --- PANEL PRINCIPAL ---
st.title("📊 Dashboard de Gestión Salarial USM")

if not st.session_state.historial:
    st.info("Carga tus liquidaciones en el panel lateral para generar el análisis visual.")
else:
    df = pd.DataFrame(st.session_state.historial)
    df["Bruto"] = df["Base"] + df["Bono"]
    HORAS_MES = 190.6
    ultimo = df.iloc[-1]

    # 1. Métricas de Resumen
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sueldo Líquido", f"$ {ultimo['Liquido']:,.0f}")
    c2.metric("Bruto (Base + Bono)", f"$ {ultimo['Bruto']:,.0f}")
    c3.metric("Valor Hora Líq.", f"$ {(ultimo['Liquido']/HORAS_MES):,.0f}")
    c4.metric("Valor Hora Bruto", f"$ {(ultimo['Bruto']/HORAS_MES):,.0f}")

    st.divider()

    # 2. Gráfico de Evolución Temporal (Líneas)
    st.subheader("📈 Evolución de Ingresos")
    fig_line = px.line(df, x="Mes", y=["Bruto", "Liquido"], markers=True,
                       title="Tendencia de Sueldo Bruto vs Líquido",
                       color_discrete_map={"Bruto": "#3366CC", "Liquido": "#109618"},
                       template="plotly_white")
    st.plotly_chart(fig_line, use_container_width=True)

    # 3. Gráficos Comparativos (Barras)
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🔹 Comparativa Sueldo Bruto")
        fig_bruto = px.bar(df, x="Mes", y="Bruto", text_auto='.3s',
                           color_discrete_sequence=['#3366CC'])
        st.plotly_chart(fig_bruto, use_container_width=True)
        
    with col2:
        st.subheader("🔸 Comparativa Sueldo Líquido")
        fig_liq = px.bar(df, x="Mes", y="Liquido", text_auto='.3s',
                         color_discrete_sequence=['#109618'])
        st.plotly_chart(fig_liq, use_container_width=True)

    st.divider()

    # 4. Tabla de Detalle Mensual
    st.subheader("📋 Desglose del Historial Procesado")
    df_display = df.copy()
    df_display["V. Hora Liq"] = df_display["Liquido"] / HORAS_MES
    
    st.dataframe(df_display.style.format({
        "Base": "$ {:,.0f}", 
        "Bono": "$ {:,.0f}", 
        "Liquido": "$ {:,.0f}", 
        "Bruto": "$ {:,.0f}",
        "V. Hora Liq": "$ {:,.0f}"
    }), use_container_width=True)

    # 5. Gráfico de Torta (Último Mes)
    st.subheader(f"🎯 Composición del Sueldo: {ultimo['Mes']}")
    df_pie = pd.DataFrame({
        "Concepto": ["Sueldo Base", "Anticipo USM"],
        "Monto": [ultimo["Base"], ultimo["Bono"]]
    })
    fig_pie = px.pie(df_pie, values="Monto", names="Concepto", hole=0.4,
                     color_discrete_sequence=px.colors.qualitative.Pastel)
    st.plotly_chart(fig_pie, use_container_width=True)
