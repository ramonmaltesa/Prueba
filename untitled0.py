import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

# --- 1) CONFIGURACIÓN Y MODELO DE DATOS ---
st.set_page_config(page_title="Gestión Salarial USM", layout="wide")

# Regla 3.4: Jornada 44h semanales -> 190.67 mensuales
HORAS_BASE_SEMANAL = 44.0
HORAS_MENSUALES = (HORAS_BASE_SEMANAL * 52) / 12

def limpiar_monto(texto):
    """Regla 2.3: Normalización de montos CLP"""
    if not texto: return 0
    limpio = re.sub(r'[^\d]', '', texto)
    return int(limpio) if limpio else 0

# --- 2) REGLAS DE EXTRACCIÓN (PARSING) ---

def extraer_datos_usm(file):
    with pdfplumber.open(file) as pdf:
        texto = "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
    
    lineas = [l.strip() for l in texto.split('\n') if l.strip()]
    
    # 2.1 Identificación del Periodo (YYYY-MM)
    match_periodo = re.search(r"Liquidación de sueldo\s+([A-Za-z]+)\s+(\d{4})", texto, re.I)
    meses_map = {
        "Enero": "01", "Febrero": "02", "Marzo": "03", "Abril": "04", "Mayo": "05", "Junio": "06",
        "Julio": "07", "Agosto": "08", "Septiembre": "09", "Octubre": "10", "Noviembre": "11", "Diciembre": "12"
    }
    mes_nom = match_periodo.group(1).capitalize() if match_periodo else "Enero"
    anio = match_periodo.group(2) if match_periodo else "2025"
    periodo_id = f"{anio}-{meses_map.get(mes_nom, '01')}"

    # 2.2 Secciones y Totales (Anclas)
    def buscar_total(patron, string):
        m = re.search(patron, string, re.I)
        return limpiar_monto(m.group(1)) if m else 0

    h_afectos = buscar_total(r"Total Haberes Afectos:\s*\$?\s*([\d\.]+)", texto)
    h_exentos = buscar_total(r"Total Haberes Exentos:\s*\$?\s*([\d\.]+)", texto)
    liq_pagar = buscar_total(r"Líquido a pagar:\s*\$?\s*([\d\.]+)", texto)
    
    # 2.4 Clasificación de Descuentos Legales
    # Buscamos el bloque entre Descuentos Legales y el Total
    afp = 0
    salud = 0
    impuesto = 0
    cesantia = 0
    
    capturando_legales = False
    for linea in lineas:
        if "DESCUENTOS LEGALES" in linea.upper(): capturando_legales = True; continue
        if "TOTAL DESCUENTOS LEGALES" in linea.upper(): capturando_legales = False; break
        
        if capturando_legales:
            monto = limpiar_monto(re.search(r"\$?\s?([\d\.]+)", linea).group(1)) if re.search(r"[\d\.]+", linea) else 0
            nombre = linea.upper()
            if "AFP" in nombre: afp += monto
            elif any(x in nombre for x in ["SALUD", "ISAPRE", "COLMENA", "FONASA"]): salud += monto
            elif "IMPUESTO" in nombre: impuesto += monto
            elif "CESANTIA" in nombre: cesantia += monto

    # 3.1 Regla Sueldo Bruto
    sueldo_bruto = h_afectos + h_exentos

    return {
        "Periodo": periodo_id,
        "Mes_Texto": f"{mes_nom} {anio}",
        "Bruto": sueldo_bruto,
        "Liquido": liq_pagar,
        "AFP": afp,
        "Salud": salud,
        "Impuesto": impuesto,
        "Cesantia": cesantia,
        "Otros_Desc": buscar_total(r"Total Otros Descuentos:\s*\$?\s*([\d\.]+)", texto)
    }

# --- 3) INTERFAZ Y DASHBOARDS ---

st.title("📊 Sistema de Gestión Salarial USM")

if 'db' not in st.session_state:
    st.session_state.db = []

with st.sidebar:
    st.header("📥 Carga de Datos")
    archivos = st.file_uploader("Sube tus liquidaciones PDF", type="pdf", accept_multiple_files=True)
    if st.button("Procesar Archivos"):
        if archivos:
            for arc in archivos:
                try:
                    data = extraer_datos_usm(arc)
                    # Evitar duplicados
                    st.session_state.db = [d for d in st.session_state.db if d["Periodo"] != data["Periodo"]]
                    st.session_state.db.append(data)
                except Exception as e:
                    st.error(f"Error en {arc.name}: {e}")
            st.success("¡Datos sincronizados!")
    
    if st.button("🗑️ Borrar Historial"):
        st.session_state.db = []
        st.rerun()

if st.session_state.db:
    df = pd.DataFrame(st.session_state.db).sort_values("Periodo")
    ultimo = df.iloc[-1]

    # --- DASHBOARD MENSUAL (KPIs) ---
    st.header(f"📌 Resumen: {ultimo['Mes_Texto']}")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Líquido", f"$ {ultimo['Liquido']:,.0f}")
    col2.metric("Bruto", f"$ {ultimo['Bruto']:,.0f}")
    col3.metric("Valor Hora Liq.", f"$ {(ultimo['Liquido']/HORAS_MENSUALES):,.0f}")
    col4.metric("Valor Hora Bruto", f"$ {(ultimo['Bruto']/HORAS_MENSUALES):,.0f}")

    st.divider()

    # --- DASHBOARD ANUAL (GRÁFICOS) ---
    st.subheader("📈 Evolución Histórica")
    fig_evol = px.line(df, x="Mes_Texto", y=["Bruto", "Liquido"], markers=True, 
                       title="Sueldo Bruto vs Líquido", template="plotly_white")
    st.plotly_chart(fig_evol, use_container_width=True)

    c_g1, c_g2 = st.columns(2)
    with c_g1:
        st.subheader("⚖️ Distribución de Descuentos (Último Mes)")
        df_desc = pd.DataFrame({
            "Concepto": ["AFP", "Salud", "Impuesto", "Cesantía", "Otros"],
            "Monto": [ultimo["AFP"], ultimo["Salud"], ultimo["Impuesto"], ultimo["Cesantia"], ultimo["Otros_Desc"]]
        })
        st.plotly_chart(px.pie(df_desc, values="Monto", names="Concepto", hole=0.4), use_container_width=True)
    
    with c_g2:
        st.subheader("🏛️ Retenciones Legales")
        st.plotly_chart(px.bar(df, x="Mes_Texto", y=["AFP", "Salud", "Impuesto"], barmode="group"), use_container_width=True)

    # --- TABLA DE DATOS ---
    st.subheader("📋 Detalle de Liquidaciones")
    st.dataframe(df.style.format({
        "Bruto": "$ {:,.0f}", "Liquido": "$ {:,.0f}", 
        "AFP": "$ {:,.0f}", "Salud": "$ {:,.0f}", 
        "Impuesto": "$ {:,.0f}", "Cesantia": "$ {:,.0f}", "Otros_Desc": "$ {:,.0f}"
    }), use_container_width=True)
else:
    st.info("👋 Sube tus liquidaciones PDF en el panel de la izquierda para comenzar.")
