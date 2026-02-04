import streamlit as st
import requests
import pandas as pd
import plotly.express as px

# --- 1. CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Calculadora Salarial USM",
    page_icon="🏦",
    layout="wide"
)

# --- 2. OBTENCIÓN DE INDICADORES (UF/UTM) ---
@st.cache_data(ttl=3600)
def obtener_indicadores():
    try:
        # Intentamos obtener valores reales de la API mindicador.cl
        response = requests.get("https://mindicador.cl/api")
        data = response.json()
        return float(data['uf']['valor']), float(data['utm']['valor'])
    except:
        # Valores de respaldo si la API falla (Aprox. Febrero 2024)
        return 38200.0, 66600.0

uf_hoy, utm_hoy = obtener_indicadores()

# --- 3. INTERFAZ DE USUARIO ---
st.title("📊 Calculadora de Sueldo Personalizada - USM")
st.markdown(f"**Indicadores del día:** UF: `${uf_hoy:,.2f}` | UTM: `${utm_hoy:,.0f}`")

# Sidebar para inputs
with st.sidebar:
    st.header("⚙️ Configuración de Ingresos")
    base = st.number_input("Sueldo Base", value=2409363)
    asig_fijas = st.number_input("Asignaciones Fijas (Antigüedad, Título, etc.)", value=228033)
    bono_usm = st.number_input("Bonificación USM (Bruta)", value=0)
    asig_teletrabajo = st.number_input("Asignación Teletrabajo (No imponible)", value=3810)
    
    st.header("🏥 Previsión y Salud")
    plan_isapre_uf = st.number_input("Plan Isapre Pactado (UF)", value=6.32)
    apv = st.number_input("APV Mensual (Régimen B)", value=0)
    seguro_salud = st.number_input("Seguro Complementario ($)", value=0)

# --- 4. LÓGICA DE CÁLCULO (Basada en tus liquidaciones) ---

# A. Haberes
imponible = base + asig_fijas + bono_usm
total_haberes = imponible + asig_teletrabajo

# B. Leyes Sociales
# El tope imponible para AFP/Salud es aprox 84.3 UF
tope_afp = 84.3 * uf_hoy
base_previsional = min(imponible, tope_afp)

monto_afp = base_previsional * 0.1127  # AFP Habitat (11.27%)
monto_cesantia = imponible * 0.006      # 0.6% cargo trabajador (Contrato Indefinido)

# C. Salud (Isapre)
# Se calcula el 7% legal y se compara con el plan pactado en UF
siete_por_ciento_legal = base_previsional * 0.07
costo_plan_isapre = plan_isapre_uf * uf_hoy

# En Chile, si tu plan es mayor al 7%, pagas el plan. Si el 7% es mayor, pagas el 7% (generas excedentes).
salud_total_descuento = max(siete_por_ciento_legal, costo_plan_isapre)

# D. Impuesto Único de Segunda Categoría
# La base tributable es: Imponible - AFP - Salud (solo hasta el 7% legal) - Cesantía - APV
base_tributable = imponible - monto_afp - siete_por_ciento_legal - monto_cesantia - apv
base_en_utm = base_tributable / utm_hoy

if base_en_utm <= 13.5:
    impuesto = 0
elif base_en_utm <= 30:
    impuesto = (base_tributable * 0.04) - (0.54 * utm_hoy)
elif base_en_utm <= 50:
    impuesto = (base_tributable * 0.08) - (1.74 * utm_hoy)
else:
    impuesto = (base_tributable * 0.135) - (4.49 * utm_hoy)

impuesto = max(0, impuesto)

# E. Descuento de Anticipo (Lógica específica USM para Bonos)
anticipo_descuento = bono_usm * 0.8583 if bono_usm > 0 else 0

# F. Resultado Líquido Final
total_descuentos = monto_afp + salud_total_descuento + monto_cesantia + impuesto + apv + seguro_salud + anticipo_descuento
sueldo_liquido = total_haberes - total_descuentos

# --- 5. VISUALIZACIÓN DE RESULTADOS ---
st.divider()
col_res1, col_res2, col_res3 = st.columns(3)

with col_res1:
    st.metric("Sueldo Líquido a Recibir", f"${sueldo_liquido:,.0f}")
with col_res2:
    st.metric("Total Descuentos", f"${total_descuentos:,.0f}")
with col_res3:
    st.metric("Impuesto Único", f"${impuesto:,.0f}")

# Gráfico de Torta
st.subheader("Análisis de Distribución")
data_grafico = pd.DataFrame({
    "Concepto": ["Sueldo Líquido", "AFP", "Salud (Isapre)", "Impuesto Único", "Otros (APV/Seg/Antic)"],
    "Monto": [
        sueldo_liquido, 
        monto_afp, 
        salud_total_descuento, 
        impuesto, 
        (apv + seguro_salud + anticipo_descuento)
    ]
})

fig = px.pie(
    data_grafico, 
    values='Monto', 
    names='Concepto', 
    hole=0.4,
    color_discrete_sequence=px.colors.sequential.RdBu
)
st.plotly_chart(fig, use_container_width=True)

# Valor por Hora
st.divider()
st.subheader("⏱️ Valor de tu tiempo")
# Basado en jornada de 44 horas semanales (~190.6 horas mensuales)
horas_mensuales = 190.6
v_hora_bruto = imponible / horas_mensuales
v_hora_liquido = sueldo_liquido / horas_mensuales

c_h1, c_h2 = st.columns(2)
c_h1.write(f"Valor Hora Bruto: **${v_hora_bruto:,.0f}**")
c_h2.write(f"Valor Hora Líquido: **${v_hora_liquido:,.0f}**")

# Proyección Anual
st.subheader("📅 Proyección Anual")
st.write(f"Salario Líquido Anual estimado (basado en este mes): **${(sueldo_liquido * 12):,.0f}**")
