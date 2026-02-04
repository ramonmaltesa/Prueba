import streamlit as st
import requests
import pandas as pd
import plotly.express as px

# --- 1. CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Calculadora Sueldo USM", page_icon="🏦")

# --- 2. OBTENCIÓN DE INDICADORES (UF/UTM) ---
@st.cache_data(ttl=3600)
def obtener_indicadores():
    try:
        # Intentamos obtener valores reales de la API mindicador.cl
        data = requests.get("https://mindicador.cl/api").json()
        return data['uf']['valor'], data['utm']['valor']
    except:
        # Valores de respaldo si la API falla
        return 38200.0, 66600.0

uf_hoy, utm_hoy = obtener_indicadores()

# --- 3. INTERFAZ DE USUARIO ---
st.title("📊 Calculadora de Sueldo Personalizada")
st.info(f"Indicadores del día: UF: ${uf_hoy:,.2f} | UTM: ${utm_hoy:,.0f}")

with st.sidebar:
    st.header("⚙️ Configuración")
    # Datos extraídos de tu liquidación de Dic 2025
    base = st.number_input("Sueldo Base", value=2409363)
    asig_fijas = st.number_input("Asignaciones Fijas", value=228033)
    bono_usm = st.number_input("Bonificación USM (Bruta)", value=0)
    
    st.header("🏥 Previsión y Salud")
    plan_isapre_uf = st.number_input("Plan Isapre (UF)", value=6.32)
    apv = st.number_input("APV Mensual (Régimen B)", value=0)
    seguro_salud = st.number_input("Seguro Complementario ($)", value=0)

# --- 4. CÁLCULOS LÓGICOS (Leyes Sociales e Impuestos) ---
imponible = base + asig_fijas + bono_usm
teletrabajo = 3810 # No imponible según tu liquidación

# Tope imponible AFP (aprox 84.3 UF)
tope_afp = 84.3 * uf_hoy
base_previsional = min(imponible, tope_afp)

# Descuentos Legales
afp = base_previsional * 0.1127  # AFP Habitat
cesantia = imponible * 0.006      # 0.6% Contrato Indefinido
salud_7 = base_previsional * 0.07
costo_isapre = plan_isapre_uf * uf_hoy
# En Isapre pagas el mayor entre el 7% y tu plan
salud_total = max(salud_7, costo_isapre)

# Cálculo Impuesto Único
# La base tributable descuenta AFP, el 7% de salud (tope), cesantía y APV
base_tributable = imponible - afp - salud_7 - cesantia - apv
base_utm = base_tributable / utm_hoy

# Tramos de Impuesto Único
if base_utm <= 13.5:
    impuesto = 0
elif base_utm <= 30:
    impuesto = (base_tributable * 0.04) - (0.54 * utm_hoy)
elif base_utm <= 50:
    impuesto = (base_tributable * 0.08) - (1.74 * utm_hoy)
else:
    impuesto = (base
