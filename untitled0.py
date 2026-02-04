import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

# --- CONFIGURACIÓN Y CONSTANTES ---
st.set_page_config(page_title="Gestión Salarial PRO", layout="wide")
HORAS_BASE_SEMANAL = 44.0
HORAS_MENSUALES = (HORAS_BASE_SEMANAL * 52) / 12

def limpiar_clp(texto):
    if not texto: return 0
    # Quitar $, puntos, espacios y dejar solo números
    limpio = re.sub(r'[^\d]', '', texto)
    return int(limpio) if limpio else 0

def extraer_seccion_items(lineas, inicio_ancla, fin_ancla):
    items = []
    capturando = False
    for linea in lineas:
        if inicio_ancla.upper() in linea.upper():
            capturando = True
            continue
        if fin_ancla.upper() in linea.upper():
            capturando = False
            break
        if capturando:
            # Buscar patrón: NOMBRE ... $ MONTO
            match = re.search(r'^(.*?)\s+\$?\s?([\d\.]+)', linea)
            if match:
                nombre = match.group(1).strip()
                monto = limpiar_clp(match.group(2))
                if monto > 0:
                    items.append({"nombre": nombre, "monto": monto})
    return items

def clasificar_descuentos(items):
    categorias = {"AFP": 0, "SALUD": 0, "IMPUESTO": 0, "CESANTIA": 0, "OTROS": 0}
    for item in items:
        n = item["nombre"].upper()
        if "AFP" in n: categorias["AFP"] += item["monto"]
        elif any(x in n for x in ["SALUD", "ISAPRE", "FONASA"]): categorias["SALUD"] += item["monto"]
        elif "IMPUESTO" in n: categorias["IMPUESTO"] += item["monto"]
        elif "CESANTIA" in n: categorias["CESANTIA"] += item["monto"]
        else: categorias["OTROS"] += item["monto"]
    return categorias

def procesar_liquidacion(file):
    with pdfplumber.open(file) as pdf:
        texto = "\n".join([p.extract_text() for p in pdf.pages])
    
    lineas = [l.strip() for l in texto.split('\n') if l.strip()]
    
    # 1. Periodo
    match_periodo = re.search(r"Liquidación de sueldo\s+([A-Za-z]+)\s+(\d{4})", texto, re.I)
    mes_nombre = match_periodo.group(1) if match_periodo else "Enero"
    anio = match_periodo.group(2) if match_periodo else "2025"
    
    # 2. Totales Ancla
    h_afectos = limpiar_clp(re.search(r"Total Haberes Afectos:\s+\$?\s?([\d\.]+)", texto, re.I).group(1))
    # Algunos meses no tienen haberes exentos, manejamos el error
    try: h_exentos = limpiar_clp(re.search(r"Total Haberes Exentos:\s+\$?\s?([\d\.]+)", texto, re.I).group(1))
    except: h_exentos = 0
    
    d_legales_total = limpiar_clp(re.search(r"Total Descuentos Legales:\s+\$?\s?([\d\.]+)", texto, re.I).group(1))
    liquido = limpiar_clp(re.search(r"Líquido a pagar:\s+\$?\s?([\d\.]+)", texto, re.I).group(1))
    
    # 3. Items Detallados
    items_legales = extraer_seccion_items(lineas, "Descuentos Legales", "Total Descuentos Legales")
    desc_clasificados = clasificar_descuentos(items_legales)
    
    return {
        "Periodo": f"{anio}-{mes_nombre}",
        "Mes_Orden": f"{anio}-{mes_nombre}", # Para ordenar después
        "Bruto": h_afectos + h_exentos,
        "Líquido": liquido,
        "AFP": desc_clasificados["AFP"],
        "Salud": desc_clasificados["SALUD"],
        "Impuesto": desc_clasificados["IMPUESTO"],
        "Otros_Desc": desc_clasificados["OTROS"] + (limpiar_clp(re.search(r"Total Otros Descuentos:\s+\$?\s?([\d\.]+)", texto, re.I).group(1)) if "Total Otros Descuentos" in texto else 0)
    }

# --- INTERFAZ ---
st.title("🏦 Dashboard de Gestión Salarial USM")

if 'db' not in st.session_state:
    st.session_state.db = []

with st.sidebar:
    st.header("📂 Carga Masiva")
    archivos = st.file_uploader("Subir Liquidaciones (PDF)", type="pdf", accept_multiple_files=True)
    if st.button("Procesar y Validar"):
        if archivos:
            for arc in archivos:
                data = procesar_liquidacion(arc)
                # Evitar duplicados
                st.session_state.db = [d for d in st.session_state.db if d["Periodo"] != data["Periodo"]]
                st.session_state.db.append(data)
            st.success(f"{len(archivos)} archivos procesados.")

if st.session_state.db:
    df = pd.DataFrame(st.session_state.db)
    df = df.sort_values("Mes_Orden")
    
    # --- DASHBOARD MENSUAL ---
    st.header("📅 Análisis Mensual")
    ultimo = df.iloc[-1]
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Último Bruto", f"$ {ultimo['Bruto']:,.0f}")
    col2.metric("Último Líquido", f"$ {ultimo['Líquido']:,.0f}")
    col3.metric("Valor Hora Bruto", f"$ {(ultimo['Bruto']/HORAS_MENSUALES):,.0f}")
    col4.metric("Valor Hora Líq.", f"$ {(ultimo['Líquido']/HORAS_MENSUALES):,.0f}")
    
    st.divider()
    
    # Gráfico Barras: Bruto vs Líquido
    fig_evol = px.bar(df, x="Periodo", y=["Bruto", "Líquido"], barmode="group",
                      title="Comparativa Mensual: Bruto vs Líquido",
                      color_discrete_map={"Bruto": "#3366CC", "Líquido": "#109618"})
    st.plotly_chart(fig_evol, use_container_width=True)
    
    # Gráfico Líneas: Retenciones Legales
    st.subheader("📉 Evolución de Descuentos Legales")
    fig_desc = px.line(df, x="Periodo", y=["AFP", "Salud", "Impuesto"], markers=True,
                       title="Detalle de Retenciones Mensuales")
    st.plotly_chart(fig_desc, use_container_width=True)

    # --- DASHBOARD ANUAL ---
    st.divider()
    st.header("🗓️ Consolidado Anual")
    resumen_anual = df.copy()
    resumen_anual['Año'] = resumen_anual['Periodo'].apply(lambda x: x.split('-')[0])
    df_anual = resumen_anual.groupby('Año').sum(numeric_only=True).reset_index()
    
    c_a1, c_a2, c_a3 = st.columns(3)
    c_a1.metric("Bruto Anual Acum.", f"$ {df_anual['Bruto'].sum():,.0f}")
    c_a2.metric("Líquido Anual Acum.", f"$ {df_anual['Líquido'].sum():,.0f}")
    c_a3.metric("Total Impuestos Año", f"$ {df_anual['Impuesto'].sum():,.0f}")

    # Tabla Detallada
    st.subheader("📋 Registro Histórico de Liquidaciones")
    st.dataframe(df.drop(columns=['Mes_Orden']).style.format({
        "Bruto": "$ {:,.0f}", "Líquido": "$ {:,.0f}", 
        "AFP": "$ {:,.0f}", "Salud": "$ {:,.0f
