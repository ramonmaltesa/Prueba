import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

# --- 1) CONFIGURACIÓN ---
st.set_page_config(page_title="Gestión Salarial USM PRO", layout="wide")
HORAS_MENSUALES = (44.0 * 52) / 12

def limpiar_monto(texto):
    if not texto: return 0
    limpio = re.sub(r'[^\d]', '', texto)
    return int(limpio) if limpio else 0

def extraer_datos_por_pagina(pagina_texto):
    """Aplica las reglas de anclas a cada página individualmente"""
    lineas = [l.strip() for l in pagina_texto.split('\n') if l.strip()]
    
    # 2.1 Identificación del periodo
    match_p = re.search(r"Liquidación de sueldo\s+([A-Za-z]+)\s+(\d{4})", pagina_texto, re.I)
    if not match_p: return None
    
    mes_nom = match_periodo.group(1).capitalize() if match_p else "Enero"
    anio = match_p.group(2)
    meses_map = {"Enero":"01","Febrero":"02","Marzo":"03","Abril":"04","Mayo":"05","Junio":"06",
                 "Julio":"07","Agosto":"08","Septiembre":"09","Octubre":"10","Noviembre":"11","Diciembre":"12"}
    periodo_id = f"{anio}-{meses_map.get(mes_nom, '01')}"
    periodo_texto = f"{mes_nom} {anio}"

    # 2.2 Totales (Anclas)
    def buscar(patron):
        m = re.search(patron, pagina_texto, re.I)
        return limpiar_monto(m.group(1)) if m else 0

    h_afectos = buscar(r"Total Haberes Afectos:\s*\$?\s*([\d\.]+)")
    h_exentos = buscar(r"Total Haberes Exentos:\s*\$?\s*([\d\.]+)")
    liq_pagar = buscar(r"Líquido a pagar:\s*\$?\s*([\d\.]+)")
    tot_legales = buscar(r"Total Descuentos Legales:\s*\$?\s*([\d\.]+)")
    tot_otros = buscar(r"Total Otros Descuentos:\s*\$?\s*([\d\.]+)")

    # 2.4 Clasificación de Descuentos Legales dentro de la página
    afp, salud, impuesto, cesantia = 0, 0, 0, 0
    capturando = False
    for linea in lineas:
        if "DESCUENTOS LEGALES" in linea.upper(): capturando = True; continue
        if "TOTAL DESCUENTOS LEGALES" in linea.upper(): capturando = False; break
        if capturando:
            m = re.search(r"\$?\s?([\d\.]+)", linea)
            monto = limpiar_monto(m.group(1)) if m else 0
            nombre = linea.upper()
            if "AFP" in nombre: afp += monto
            elif any(x in nombre for x in ["SALUD", "ISAPRE", "COLMENA", "FONASA"]): salud += monto
            elif "IMPUESTO" in nombre: impuesto += monto
            elif "CESANTIA" in nombre: cesantia += monto

    return {
        "ID": periodo_id,
        "Mes": periodo_texto,
        "Bruto": h_afectos + h_exentos,
        "Liquido": liq_pagar,
        "AFP": afp,
        "Salud": salud,
        "Impuesto": impuesto,
        "Cesantia": cesantia,
        "Otros_Desc": tot_otros
    }

# --- 2) INTERFAZ ---
if 'base_datos' not in st.session_state:
    st.session_state.base_datos = []

with st.sidebar:
    st.header("📥 Carga de Documentos")
    archivo = st.file_uploader("Sube tu PDF con múltiples meses", type="pdf")
    if st.button("Procesar Historial Completo"):
        if archivo:
            with pdfplumber.open(archivo) as pdf:
                for page in pdf.pages:
                    texto_pag = page.extract_text()
                    datos = extraer_datos_por_pagina(texto_pag)
                    if datos:
                        # Reemplaza si ya existe el mes, evita duplicados
                        st.session_state.base_datos = [d for d in st.session_state.base_datos if d["ID"] != datos["ID"]]
                        st.session_state.base_datos.append(datos)
            st.success("¡Todos los meses procesados!")

# --- 3) VISUALIZACIÓN ---
if st.session_state.base_datos:
    df = pd.DataFrame(st.session_state.base_datos).sort_values("ID")
    
    st.title("📊 Análisis Histórico USM")
    
    # KPIs del ÚLTIMO MES (Enero 2025 en tu caso)
    ultimo = df.iloc[-1]
    st.subheader(f"📍 Último periodo detectado: {ultimo['Mes']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sueldo Líquido", f"$ {ultimo['Liquido']:,.0f}")
    c2.metric("Sueldo Bruto", f"$ {ultimo['Bruto']:,.0f}")
    c3.metric("Valor Hora Liq.", f"$ {(ultimo['Liquido']/HORAS_MENSUALES):,.0f}")
    c4.metric("Impuesto Único", f"$ {ultimo['Impuesto']:,.0f}")

    st.divider()

    # GRÁFICOS SOLICITADOS
    st.subheader("📈 Evolución de Ingresos")
    fig_evol = px.line(df, x="Mes", y=["Bruto", "Liquido"], markers=True, 
                       title="Sueldo Bruto vs Líquido por Mes",
                       color_discrete_map={"Bruto": "#3366CC", "Liquido": "#109618"})
    st.plotly_chart(fig_evol, use_container_width=True)

    col_izq, col_der = st.columns(2)
    with col_izq:
        st.subheader("💰 Distribución de Retenciones")
        fig_bar = px.bar(df, x="Mes", y=["AFP", "Salud", "Impuesto"], 
                         title="Descuentos Legales Mensuales", barmode="stack")
        st.plotly_chart(fig_bar, use_container_width=True)
    
    with col_der:
        st.subheader("📋 Datos Consolidados")
        st.dataframe(df[["Mes", "Bruto", "Liquido", "Impuesto", "AFP", "Salud"]].style.format({
            "Bruto": "$ {:,.0f}", "Liquido": "$ {:,.0f}", "Impuesto": "$ {:,.0f}", 
            "AFP": "$ {:,.0f}", "Salud": "$ {:,.0f}"
        }), use_container_width=True)
else:
    st.info("Carga el PDF para extraer todos los meses disponibles (Septiembre 2024 - Enero 2025).")
