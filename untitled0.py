import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

# --- 1) CONFIGURACIÓN Y REGLAS DE CÁLCULO ---
st.set_page_config(page_title="Gestión Salarial PRO", layout="wide")

# Regla 3.4: Valor hora basado en 44h semanales
HORAS_BASE_SEMANAL = 44.0
HORAS_MENSUALES = (HORAS_BASE_SEMANAL * 52) / 12  # ≈ 190,67

# --- 2) FUNCIONES DE EXTRACCIÓN (PARSING) ---

def limpiar_monto(texto):
    """Regla 2.3: Normalizar montos a entero CLP"""
    if not texto: return 0
    limpio = re.sub(r'[^\d]', '', texto)
    return int(limpio) if limpio else 0

def extraer_items_bloque(lineas, inicio_ancla, fin_ancla):
    """Regla 2.3: Leer items entre anclas estables"""
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
            # Patrón: NOMBRE ... $ MONTO
            match = re.search(r'^(.*?)\s+\$?\s?([\d\.]+)', linea)
            if match:
                items.append({
                    "nombre": match.group(1).strip(),
                    "monto": limpiar_monto(match.group(2))
                })
    return items

def procesar_pdf_ia(file):
    """Regla 2: Reglas de extracción desde PDF"""
    with pdfplumber.open(file) as pdf:
        texto = "\n".join([p.extract_text() for p in pdf.pages])
    
    lineas = [l.strip() for l in texto.split('\n') if l.strip()]
    
    # 2.1 Identificación del periodo
    match_p = re.search(r"Liquidación de sueldo\s+([A-Za-z]+)\s+(\d{4})", texto, re.I)
    periodo = f"{match_p.group(2)}-{match_p.group(1)}" if match_p else "Desconocido"

    # 2.2 Secciones y Totales (Anclas)
    h_afectos = limpiar_monto(re.search(r"Total Haberes Afectos:\s+\$?\s?([\d\.]+)", texto, re.I).group(1))
    
    # Haberes Exentos (Opcional según regla 2.2)
    h_exento_match = re.search(r"Total Haberes Exentos:\s+\$?\s?([\d\.]+)", texto, re.I)
    h_exentos = limpiar_monto(h_exento_match.group(1)) if h_exento_match else 0
    
    liq_pagar = limpiar_monto(re.search(r"Líquido a pagar:\s+\$?\s?([\d\.]+)", texto, re.I).group(1))
    
    # 2.
