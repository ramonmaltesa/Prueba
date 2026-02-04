import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

st.set_page_config(page_title="IA Salarial USM", layout="wide")

def limpiar_monto_pro(t):
    if not t: return 0.0
    # Quitamos símbolos pero mantenemos la estructura numérica
    limpio = re.sub(r'[^\d,.]', '', t)
    
    # Si el número es excesivamente largo (más de 8 dígitos), 
    # probablemente es un RUT o Folio, no un monto de sueldo.
    if len(re.sub(r'[^\d]', '', limpio)) > 8:
        return 0.0

    if limpio.count('.') >= 1 and "," in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    elif limpio.count('.') > 1:
        limpio = limpio.replace(".", "")
    elif "," in limpio:
        limpio = limpio.replace(",", ".")
        
    try:
        val = float(limpio)
        return val if val < 10000000 else 0.0 # Filtro de seguridad: nada sobre 10M
    except:
        return 0.0

def analizador_ia_semantico(texto):
    """
    Motor que analiza el contexto de las palabras para no confundir 
    números de cuenta con sueldos.
    """
    datos = {"Mes": "Desconocido", "Base": 0.0, "Bono": 0.0, "Liquido": 0.0}
    
    # 1. Extraer Mes
    meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
             "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    for m in meses:
        if m.upper() in texto.upper():
            anio = re.search(r"202\d", texto)
            datos["Mes"] = f"{m} {anio.group(0) if anio else ''}"
            break

    # 2. Análisis por bloques de contexto
    lineas = texto.split('\n')
    for linea in lineas:
        linea_u = linea.upper()
        
        # Solo procesamos números si la línea contiene palabras clave financieras
        if any(key in linea_u for key in ["BASE", "BONO", "BONIF", "PAGAR", "LIQUIDO", "ALCANCE"]):
            numeros = re.findall(r'(\d[\d\.\,]+)', linea)
            if not numeros: continue
            
            valor = limpiar_monto_pro(numeros[-1])
            
            if "BASE" in linea_u:
                datos["Base"] = valor
            elif "BONO" in linea_u or "BONIF" in linea_u or "ASIG" in linea_u:
                # Sumamos solo si no es el mismo sueldo base
                if valor != datos["Base"]:
                    datos["Bono"] += valor
            elif any(k in linea_u for k in ["PAGAR", "LIQUIDO", "PERCIBIR"]):
                datos["Liquido"] = valor
                
    return datos

# --- INTERFAZ ---
st.title("🤖 IA Salarial USM (Versión Anti-Errores)")

if 'historial' not in st.session_state:
    st.session_state.historial = []

with st.sidebar:
    st.header("📥 Carga de PDFs")
    archivos = st.file_uploader("Sube tus liquidaciones", type="pdf", accept_multiple_files=True)
    if st.button("Ejecutar Análisis IA"):
        if archivos:
            for arc in archivos:
                with pdfplumber.open(arc) as pdf:
                    texto = "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
                res = analizador_ia_semantico(texto)
                if res["Liquido"] > 0: # Solo agregar si la lectura fue exitosa
                    st.session_state.historial = [h for h in st.session_state.historial if h["Mes"] != res["Mes"]]
                    st.session_state.historial.append(res)
            st.success("¡Análisis Finalizado!")

if st.session_state.historial:
    df = pd.DataFrame(st.session_state.historial)
    df["Bruto"] = df["Base"] + df["Bono"]
    
    # Métricas limpias
    ult = df.iloc[-1]
    c1, c2, c3 = st.columns(3)
    c1.metric("Líquido Real", f"$ {ult['Liquido']:,.0f}")
    c2.metric("Bono Real", f"$ {ult['Bono']:,.0f}")
    c3.metric("Sueldo Base", f"$ {ult['Base']:,.0f}")

    st.divider()
    st.subheader("📋 Historial Corregido")
    st.dataframe(df.style.format({"Base": "$ {:,.0f}", "Bono": "$ {:,.0f}", "Liquido": "$ {:,.0f}", "Bruto": "$ {:,.0f}"}), use_container_width=True)
    
    st.subheader("📈 Tendencia de Ingresos")
    fig = px.line(df, x="Mes", y=["Liquido", "Bruto"], markers=True)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Carga tus PDFs para corregir los valores.")
