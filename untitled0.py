import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import pdfplumber
import re

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Historial Salarial USM", layout="wide")

# Función para limpiar montos
def limpiar_monto(texto):
    if not texto: return 0.0
    limpio = re.sub(r"[^\d,]", "", texto).replace(",", ".")
    try: return float(limpio)
    except: return 0.0

# --- EXTRACCIÓN DE DATOS ---
def extraer_datos_pdf(file):
    texto_completo = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto_completo += page.extract_text() + "\n"
    
    # Extraer Mes y Año (Ej: Septiembre 2024)
    periodo_match = re.search(r"Liquidación de sueldo\s+([A-Za-z]+\s+\d{4})", texto_completo)
    periodo = periodo_match.group(1) if periodo_match else "Desconocido"
    
    # Extraer valores específicos
    base = re.search(r"SUELDO BASE\s+\$?\s?([\d.]+)", texto_completo)
    bono = re.search(r"BONIFICACION USM\s+\$?\s?([\d.]+)", texto_completo)
    liquido = re.search(r"TOTAL A PAGAR\s+\$?\s?([\d.]+)", texto_completo) # O "ALCANCE LIQUIDO"
    
    return {
        "Mes": periodo,
        "Bruto": limpiar_monto(base.group(1)) if base else 0.0,
        "Bono": limpiar_monto(bono.group(1)) if bono else 0.0,
        "Líquido": limpiar_monto(liquido.group(1)) if liquido else 0.0
    }

# --- ESTADO DE LA APLICACIÓN (Base de Datos) ---
if 'historial' not in st.session_state:
    # Datos iniciales basados en tus archivos para que no esté vacío
    st.session_state.historial = [
        {"Mes": "Septiembre 2024", "Bruto": 2305611, "Bono": 782386, "Líquido": 1930130},
        {"Mes": "Enero 2025", "Bruto": 2409363, "Bono": 933815, "Líquido": 2041503}
    ]

# --- INTERFAZ ---
st.title("📈 Historial y Evolución Salarial USM")

# 1. Zona de Carga
with st.sidebar:
    st.header("Cargar Liquidaciones")
    archivos = st.file_uploader("Sube uno o varios PDFs", type="pdf", accept_multiple_files=True)
    
    if st.button("Procesar y Guardar"):
        if archivos:
            for arc in archivos:
                datos = extraer_datos_pdf(arc)
                # Evitar duplicados por mes
                if datos["Mes"] not in [x["Mes"] for x in st.session_state.historial]:
                    st.session_state.historial.append(datos)
            st.success("¡Historial actualizado!")

# 2. Visualización de Datos
df_hist = pd.DataFrame(st.session_state.historial)

# Métricas del último mes cargado
if not df_hist.empty:
    ultimo = df_hist.iloc[-1]
    c1, c2, c3 = st.columns(3)
    c1.metric("Último Bruto", f"$ {ultimo['Bruto']:,.0f}")
    c2.metric("Último Líquido", f"$ {ultimo['Líquido']:,.0f}")
    c3.metric("Bono Detectado", f"$ {ultimo['Bono']:,.0f}")

st.divider()

# 3. Gráfico de Evolución Temporal
st.subheader("Evolución de Ingresos por Mes")
if not df_hist.empty:
    # Preparar datos para gráfico (unir Bruto + Bono para ver el total afecto)
    df_plot = df_hist.copy()
    df_plot["Total Bruto"] = df_plot["Bruto"] + df_plot["Bono"]
    
    fig_evol = px.line(df_plot, x="Mes", y=["Total Bruto", "Líquido"], 
                       markers=True, 
                       title="Comparativa Bruto vs Líquido a través del tiempo",
                       labels={"value": "Monto ($)", "variable": "Tipo de Sueldo"})
    st.plotly_chart(fig_evol, use_container_width=True)

st.divider()

# 4. Tabla de Detalle (Lo que pediste)
st.subheader("Detalle Cronológico de Liquidaciones")
st.table(df_hist.style.format({
    "Bruto": "$ {:,.0f}",
    "Bono": "$ {:,.0f}",
    "Líquido": "$ {:,.0f}"
}))

# 5. Exportar
st.download_button(
    label="Descargar Reporte en Excel (CSV)",
    data=df_hist.to_csv(index=False).encode('utf-8'),
    file_name='historial_sueldos_usm.csv',
    mime='text/csv',
)
