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
    # Elimina todo lo que no sea número
    limpio = re.sub(r'[^\d]', '', texto)
    return int(limpio) if limpio else 0

def extraer_datos_por_pagina(pagina_texto):
    """Extrae datos de una página individual del PDF"""
    lineas = [l.strip() for l in pagina_texto.split('\n') if l.strip()]
    
    # 2.1 Identificación del periodo (Corregido el error de nombre de variable)
    match_p = re.search(r"Liquidación de sueldo\s+([A-Za-z]+)\s+(\d{4})", pagina_texto, re.I)
    if not match_p: 
        return None
    
    mes_nom = match_p.group(1).capitalize()
    anio = match_p.group(2)
    
    meses_map = {
        "Enero":"01","Febrero":"02","Marzo":"03","Abril":"04","Mayo":"05","Junio":"06",
        "Julio":"07","Agosto":"08","Septiembre":"09","Octubre":"10","Noviembre":"11","Diciembre":"12"
    }
    
    periodo_id = f"{anio}-{meses_map.get(mes_nom, '01')}"
    periodo_texto = f"{mes_nom} {anio}"

    # 2.2 Totales (Anclas)
    def buscar_monto(patron):
        m = re.search(patron, pagina_texto, re.I)
        return limpiar_monto(m.group(1)) if m else 0

    h_afectos = buscar_monto(r"Total Haberes Afectos:\s*\$?\s*([\d\.]+)")
    h_exentos = buscar_monto(r"Total Haberes Exentos:\s*\$?\s*([\d\.]+)")
    liq_pagar = buscar_monto(r"Líquido a pagar:\s*\$?\s*([\d\.]+)")
    
    # Clasificación de Descuentos Legales
    afp, salud, impuesto, cesantia = 0, 0, 0, 0
    capturando = False
    for linea in lineas:
        l_up = linea.upper()
        if "DESCUENTOS LEGALES" in l_up: capturando = True; continue
        if "TOTAL DESCUENTOS LEGALES" in l_up: capturando = False; break
        
        if capturando:
            m = re.search(r"\$?\s?([\d\.]+)", linea)
            if m:
                monto = limpiar_monto(m.group(1))
                if "AFP" in l_up: afp += monto
                elif any(x in l_up for x in ["SALUD", "ISAPRE", "COLMENA", "FONASA"]): salud += monto
                elif "IMPUESTO" in l_up: impuesto += monto
                elif "CESANTIA" in l_up: cesantia += monto

    return {
        "ID": periodo_id,
        "Mes": periodo_texto,
        "Bruto": h_afectos + h_exentos,
        "Liquido": liq_pagar,
        "AFP": afp,
        "Salud": salud,
        "Impuesto": impuesto,
        "Cesantia": cesantia
    }

# --- 2) LÓGICA DE CARGA ---
if 'base_datos' not in st.session_state:
    st.session_state.base_datos = []

with st.sidebar:
    st.header("📥 Carga de Documentos")
    archivo = st.file_uploader("Sube tu PDF (Multi-mes)", type="pdf")
    if st.button("Procesar Liquidaciones"):
        if archivo:
            with pdfplumber.open(archivo) as pdf:
                for page in pdf.pages:
                    texto_pag = page.extract_text()
                    if texto_pag:
                        datos = extraer_datos_por_pagina(texto_pag)
                        if datos:
                            # Actualizar si ya existe el mes
                            st.session_state.base_datos = [d for d in st.session_state.base_datos if d["ID"] != datos["ID"]]
                            st.session_state.base_datos.append(datos)
            st.success(f"Se procesaron {len(st.session_state.base_datos)} meses correctamente.")

# --- 3) DASHBOARD ---
if st.session_state.base_datos:
    df = pd.DataFrame(st.session_state.base_datos).sort_values("ID")
    
    st.title("📈 Dashboard Salarial Histórico")
    
    # Resumen Último Mes
    ult = df.iloc[-1]
    st.subheader(f"Resumen de {ult['Mes']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Líquido", f"$ {ult['Liquido']:,.0f}")
    c2.metric("Bruto", f"$ {ult['Bruto']:,.0f}")
    c3.metric("Valor Hora Liq.", f"$ {(ult['Liquido']/HORAS_MENSUALES):,.0f}")
    c4.metric("Impuestos", f"$ {ult['Impuesto']:,.0f}")

    st.divider()

    # Gráfico de Evolución
    st.plotly_chart(px.line(df, x="Mes", y=["Bruto", "Liquido"], markers=True, 
                            title="Evolución Bruto vs Líquido",
                            color_discrete_map={"Bruto": "#3366CC", "Liquido": "#109618"}), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🏛️ Descuentos Legales")
        st.plotly_chart(px.bar(df, x="Mes", y=["AFP", "Salud", "Impuesto"], 
                               title="Retenciones por Categoría"), use_container_width=True)
    with col2:
        st.subheader("📋 Detalle Histórico")
        st.dataframe(df.style.format({
            "Bruto": "$ {:,.0f}", "Liquido": "$ {:,.0f}", "AFP": "$ {:,.0f}", 
            "Salud": "$ {:,.0f}", "Impuesto": "$ {:,.0f}", "Cesantia": "$ {:,.0f}"
        }), use_container_width=True)
else:
    st.info("Carga el archivo PDF para ver el desglose de todos los meses.")
