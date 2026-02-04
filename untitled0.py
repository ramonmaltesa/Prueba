import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pdfplumber
import re
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

# --- CONFIGURACIÓN ---
st.set_page_config(
    page_title="Gestión Salarial USM PRO", 
    layout="wide",
    initial_sidebar_state="expanded"
)

HORAS_MENSUALES_BASE = (44.0 * 52) / 12  # ~190.67 horas/mes

# --- MODELO DE DATOS ---
@dataclass
class ItemDescuento:
    nombre: str
    monto: int
    tipo: str  # 'descuento_legal' o 'descuento_otro'
    categoria: str  # 'AFP', 'SALUD', 'IMPUESTO', 'CESANTIA', 'OTRO'

@dataclass
class ItemHaber:
    nombre: str
    monto: int
    tipo: str  # 'haber_afecto' o 'haber_exento'

@dataclass
class LiquidacionMensual:
    periodo: str  # YYYY-MM
    mes_nombre: str  # "Enero 2025"
    
    # Información básica
    dias_trabajados: int
    dias_licencia: int
    dias_ausencia: int
    dias_vacaciones: int
    horas_base_semanal: float
    sueldo_base: int
    
    # Haberes
    haberes_afectos_total: int
    haberes_exentos_total: int
    haberes_items: List[ItemHaber]
    
    # Descuentos
    descuentos_legales_total: int
    otros_descuentos_total: int
    descuentos_items: List[ItemDescuento]
    
    # Resultados
    liquido_a_pagar: int
    total_imponible: int
    total_tributable: int
    
    # Validaciones
    validacion_haberes_ok: bool = True
    validacion_descuentos_ok: bool = True
    mensajes_validacion: List[str] = None

# --- UTILIDADES DE LIMPIEZA ---
def limpiar_monto(texto: str) -> int:
    """Extrae y convierte un monto a entero, manejando formatos chilenos."""
    if not texto:
        return 0
    # Quitar todo excepto dígitos
    limpio = re.sub(r'[^\d]', '', texto)
    return int(limpio) if limpio else 0

def normalizar_mes(mes_nombre: str) -> str:
    """Convierte nombre de mes a número (01-12)."""
    meses_map = {
        "ENERO": "01", "FEBRERO": "02", "MARZO": "03", "ABRIL": "04",
        "MAYO": "05", "JUNIO": "06", "JULIO": "07", "AGOSTO": "08",
        "SEPTIEMBRE": "09", "OCTUBRE": "10", "NOVIEMBRE": "11", "DICIEMBRE": "12"
    }
    return meses_map.get(mes_nombre.upper(), "01")

# --- EXTRACCIÓN MEJORADA ---
def extraer_liquidacion_desde_pagina(texto_pagina: str) -> Optional[LiquidacionMensual]:
    """
    Extrae datos completos de una liquidación siguiendo el modelo de datos.
    Implementa todas las reglas de extracción del documento de especificaciones.
    """
    lineas = [l.strip() for l in texto_pagina.split('\n') if l.strip()]
    
    # 1. IDENTIFICACIÓN DEL PERIODO
    match_periodo = re.search(r"Liquidación de sueldo\s+([A-Za-z]+)\s+(\d{4})", texto_pagina, re.I)
    if not match_periodo:
        return None
    
    mes_nombre = match_periodo.group(1).capitalize()
    anio = match_periodo.group(2)
    periodo = f"{anio}-{normalizar_mes(mes_nombre)}"
    mes_completo = f"{mes_nombre} {anio}"
    
    # 2. INFORMACIÓN BÁSICA (Cabecera)
    def extraer_valor(patron: str, default=0) -> int:
        m = re.search(patron, texto_pagina, re.I)
        if m:
            return limpiar_monto(m.group(1))
        return default
    
    dias_trabajados = extraer_valor(r"Días trabajados:\s*(\d+)")
    dias_licencia = extraer_valor(r"Días licencia:\s*(\d+)")
    dias_ausencia = extraer_valor(r"Días Ausencia:\s*(\d+)")
    dias_vacaciones = extraer_valor(r"Días vacaciones:\s*(\d+)")
    
    # Horas base (puede ser decimal)
    match_horas = re.search(r"Horas base:\s*([\d\.]+)", texto_pagina, re.I)
    horas_base = float(match_horas.group(1)) if match_horas else 44.0
    
    sueldo_base = extraer_valor(r"Sueldo base:\s*\$?\s*([\d\.]+)")
    
    # 3. TOTALES (Anclas principales)
    haberes_afectos_total = extraer_valor(r"Total Haberes Afectos:\s*\$\s*([\d\.]+)")
    haberes_exentos_total = extraer_valor(r"Total Haberes Exentos:\s*\$\s*([\d\.]+)")
    descuentos_legales_total = extraer_valor(r"Total Descuentos Legales:\s*\$\s*([\d\.]+)")
    otros_descuentos_total = extraer_valor(r"Total Otros Descuentos:\s*\$\s*([\d\.]+)")
    liquido_a_pagar = extraer_valor(r"Líquido a pagar:\s*\$\s*([\d\.]+)")
    total_imponible = extraer_valor(r"Total Imponible\s*\$?\s*([\d\.]+)")
    total_tributable = extraer_valor(r"Total Tributable\s*\$?\s*([\d\.]+)")
    
    # 4. EXTRACCIÓN DE ITEMS (Haberes y Descuentos)
    haberes_items = []
    descuentos_items = []
    
    # Extraer Haberes Afectos
    haberes_afectos_dict = extraer_items_seccion(
        lineas, 
        "HABERES AFECTOS", 
        "TOTAL HABERES AFECTOS",
        "haber_afecto"
    )
    for item in haberes_afectos_dict:
        haberes_items.append(ItemHaber(
            nombre=item['nombre'],
            monto=item['monto'],
            tipo='haber_afecto'
        ))
    
    # Extraer Haberes Exentos
    haberes_exentos_dict = extraer_items_seccion(
        lineas, 
        "HABERES EXENTOS", 
        "TOTAL HABERES EXENTOS",
        "haber_exento"
    )
    for item in haberes_exentos_dict:
        haberes_items.append(ItemHaber(
            nombre=item['nombre'],
            monto=item['monto'],
            tipo='haber_exento'
        ))
    
    # Extraer Descuentos Legales
    descuentos_legales = extraer_items_seccion(
        lineas, 
        "DESCUENTOS LEGALES", 
        "TOTAL DESCUENTOS LEGALES",
        "descuento_legal"
    )
    
    # Clasificar descuentos legales por categoría
    for item in descuentos_legales:
        categoria = clasificar_descuento(item['nombre'])
        descuentos_items.append(ItemDescuento(
            nombre=item['nombre'],
            monto=item['monto'],
            tipo='descuento_legal',
            categoria=categoria
        ))
    
    # Extraer Otros Descuentos
    otros_desc = extraer_items_seccion(
        lineas, 
        "OTROS DESCUENTOS", 
        "TOTAL OTROS DESCUENTOS",
        "descuento_otro"
    )
    
    for item in otros_desc:
        descuentos_items.append(ItemDescuento(
            nombre=item['nombre'],
            monto=item['monto'],
            tipo='descuento_otro',
            categoria='OTRO'
        ))
    
    # 5. VALIDACIONES
    validaciones = validar_liquidacion(
        haberes_items,
        haberes_afectos_total,
        haberes_exentos_total,
        descuentos_items,
        descuentos_legales_total,
        otros_descuentos_total
    )
    
    # Crear objeto LiquidacionMensual
    liquidacion = LiquidacionMensual(
        periodo=periodo,
        mes_nombre=mes_completo,
        dias_trabajados=dias_trabajados,
        dias_licencia=dias_licencia,
        dias_ausencia=dias_ausencia,
        dias_vacaciones=dias_vacaciones,
        horas_base_semanal=horas_base,
        sueldo_base=sueldo_base,
        haberes_afectos_total=haberes_afectos_total,
        haberes_exentos_total=haberes_exentos_total,
        haberes_items=haberes_items,
        descuentos_legales_total=descuentos_legales_total,
        otros_descuentos_total=otros_descuentos_total,
        descuentos_items=descuentos_items,
        liquido_a_pagar=liquido_a_pagar,
        total_imponible=total_imponible,
        total_tributable=total_tributable,
        validacion_haberes_ok=validaciones['haberes_ok'],
        validacion_descuentos_ok=validaciones['descuentos_ok'],
        mensajes_validacion=validaciones['mensajes']
    )
    
    return liquidacion

def extraer_items_seccion(lineas: List[str], inicio: str, fin: str, tipo: str) -> List[Dict]:
    """Extrae items entre dos anclas (ej: entre 'Haberes Afectos' y 'Total Haberes Afectos')."""
    items = []
    capturando = False
    
    for linea in lineas:
        linea_upper = linea.upper()
        
        # Detectar inicio de sección
        if inicio in linea_upper and "TOTAL" not in linea_upper:
            capturando = True
            continue
        
        # Detectar fin de sección
        if fin in linea_upper:
            capturando = False
            break
        
        if capturando:
            # Buscar patrón: NOMBRE ... $ MONTO
            match = re.search(r'^(.+?)\s+\$\s*([\d\.]+)\s*$', linea)
            if match:
                nombre = match.group(1).strip()
                monto = limpiar_monto(match.group(2))
                
                # Filtrar líneas que no son items reales
                if monto > 0 and len(nombre) > 3:
                    items.append({
                        'nombre': nombre,
                        'monto': monto,
                        'tipo': tipo
                    })
    
    return items

def clasificar_descuento(nombre: str) -> str:
    """Clasifica un descuento en categorías: AFP, SALUD, IMPUESTO, CESANTIA, OTRO."""
    nombre_upper = nombre.upper()
    
    if "AFP" in nombre_upper or "COTIZACION" in nombre_upper:
        return "AFP"
    elif any(x in nombre_upper for x in ["SALUD", "ISAPRE", "COLMENA"]):
        return "SALUD"
    elif "IMPUESTO" in nombre_upper:
        return "IMPUESTO"
    elif "CESANTIA" in nombre_upper or "CESANTÍA" in nombre_upper:
        return "CESANTIA"
    else:
        return "OTRO"

def validar_liquidacion(haberes_items, haberes_afectos_total, haberes_exentos_total,
                        descuentos_items, descuentos_legales_total, otros_descuentos_total) -> Dict:
    """Valida que los totales coincidan con las sumas de items."""
    mensajes = []
    
    # Validar Haberes Afectos
    suma_afectos = sum(h.monto for h in haberes_items if h.tipo == 'haber_afecto')
    haberes_ok = abs(suma_afectos - haberes_afectos_total) <= 1  # Tolerancia de 1 peso
    
    if not haberes_ok:
        mensajes.append(f"⚠️ Haberes Afectos: suma items={suma_afectos:,} vs total={haberes_afectos_total:,}")
    
    # Validar Haberes Exentos
    suma_exentos = sum(h.monto for h in haberes_items if h.tipo == 'haber_exento')
    if haberes_exentos_total > 0:
        if abs(suma_exentos - haberes_exentos_total) > 1:
            haberes_ok = False
            mensajes.append(f"⚠️ Haberes Exentos: suma items={suma_exentos:,} vs total={haberes_exentos_total:,}")
    
    # Validar Descuentos Legales
    suma_desc_legales = sum(d.monto for d in descuentos_items if d.tipo == 'descuento_legal')
    descuentos_ok = abs(suma_desc_legales - descuentos_legales_total) <= 1
    
    if not descuentos_ok:
        mensajes.append(f"⚠️ Desc. Legales: suma items={suma_desc_legales:,} vs total={descuentos_legales_total:,}")
    
    # Validar Otros Descuentos
    suma_otros_desc = sum(d.monto for d in descuentos_items if d.tipo == 'descuento_otro')
    if otros_descuentos_total > 0:
        if abs(suma_otros_desc - otros_descuentos_total) > 1:
            descuentos_ok = False
            mensajes.append(f"⚠️ Otros Desc.: suma items={suma_otros_desc:,} vs total={otros_descuentos_total:,}")
    
    return {
        'haberes_ok': haberes_ok,
        'descuentos_ok': descuentos_ok,
        'mensajes': mensajes
    }

# --- FUNCIONES DE ANÁLISIS ---
def calcular_metricas_mes(liq: LiquidacionMensual) -> Dict:
    """Calcula métricas derivadas de una liquidación."""
    bruto = liq.haberes_afectos_total + liq.haberes_exentos_total
    
    # Desglose de descuentos por categoría
    afp = sum(d.monto for d in liq.descuentos_items if d.categoria == 'AFP')
    salud = sum(d.monto for d in liq.descuentos_items if d.categoria == 'SALUD')
    impuesto = sum(d.monto for d in liq.descuentos_items if d.categoria == 'IMPUESTO')
    cesantia = sum(d.monto for d in liq.descuentos_items if d.categoria == 'CESANTIA')
    otros_desc = sum(d.monto for d in liq.descuentos_items if d.categoria == 'OTRO')
    
    # Valor hora
    horas_mes = HORAS_MENSUALES_BASE
    valor_hora_bruto = bruto / horas_mes if horas_mes > 0 else 0
    valor_hora_liquido = liq.liquido_a_pagar / horas_mes if horas_mes > 0 else 0
    
    return {
        'periodo': liq.periodo,
        'mes': liq.mes_nombre,
        'bruto': bruto,
        'liquido': liq.liquido_a_pagar,
        'afp': afp,
        'salud': salud,
        'impuesto': impuesto,
        'cesantia': cesantia,
        'otros_descuentos': otros_desc,
        'total_descuentos': liq.descuentos_legales_total + liq.otros_descuentos_total,
        'valor_hora_bruto': valor_hora_bruto,
        'valor_hora_liquido': valor_hora_liquido
    }

# --- INTERFAZ STREAMLIT ---
def main():
    # Estado de sesión
    if 'liquidaciones' not in st.session_state:
        st.session_state.liquidaciones = []
    
    # SIDEBAR: Carga de datos
    with st.sidebar:
        st.header("📥 Carga de Liquidaciones")
        
        archivo = st.file_uploader(
            "Sube tu PDF (multi-página)", 
            type="pdf",
            help="Cada página debe contener una liquidación mensual"
        )
        
        if st.button("📊 Procesar PDF", type="primary"):
            if archivo:
                with st.spinner("Procesando liquidaciones..."):
                    liquidaciones_nuevas = []
                    
                    with pdfplumber.open(archivo) as pdf:
                        for i, page in enumerate(pdf.pages, 1):
                            texto = page.extract_text()
                            liq = extraer_liquidacion_desde_pagina(texto)
                            
                            if liq:
                                liquidaciones_nuevas.append(liq)
                            else:
                                st.warning(f"No se pudo procesar la página {i}")
                    
                    # Actualizar estado (evitar duplicados por periodo)
                    periodos_existentes = {l.periodo for l in st.session_state.liquidaciones}
                    
                    for liq in liquidaciones_nuevas:
                        if liq.periodo not in periodos_existentes:
                            st.session_state.liquidaciones.append(liq)
                        else:
                            # Reemplazar si ya existe
                            st.session_state.liquidaciones = [
                                l for l in st.session_state.liquidaciones 
                                if l.periodo != liq.periodo
                            ]
                            st.session_state.liquidaciones.append(liq)
                    
                    # Ordenar por periodo
                    st.session_state.liquidaciones.sort(key=lambda x: x.periodo)
                    
                    st.success(f"✅ {len(liquidaciones_nuevas)} liquidaciones procesadas")
                    st.rerun()
        
        if st.session_state.liquidaciones:
            st.divider()
            st.metric("Total Liquidaciones", len(st.session_state.liquidaciones))
            
            # Mostrar validaciones
            validaciones_fallidas = [
                liq for liq in st.session_state.liquidaciones 
                if not (liq.validacion_haberes_ok and liq.validacion_descuentos_ok)
            ]
            
            if validaciones_fallidas:
                st.warning(f"⚠️ {len(validaciones_fallidas)} con advertencias")
                with st.expander("Ver detalles"):
                    for liq in validaciones_fallidas:
                        st.write(f"**{liq.mes_nombre}**")
                        for msg in liq.mensajes_validacion:
                            st.write(msg)
            
            if st.button("🗑️ Limpiar datos"):
                st.session_state.liquidaciones = []
                st.rerun()
    
    # MAIN CONTENT
    if not st.session_state.liquidaciones:
        st.title("📊 Gestión Salarial USM PRO")
        st.info("👈 Sube un PDF desde el panel lateral para comenzar")
        
        st.markdown("""
        ### Características:
        - ✅ Extracción automática de liquidaciones
        - ✅ Validación de totales
        - ✅ Dashboard anual y mensual
        - ✅ Análisis de descuentos
        - ✅ Valor hora bruto y líquido
        """)
        return
    
    # Crear DataFrame de métricas
    metricas = [calcular_metricas_mes(liq) for liq in st.session_state.liquidaciones]
    df = pd.DataFrame(metricas)
    
    # TABS: Dashboard Anual vs Mensual
    tab_anual, tab_mensual, tab_detalle = st.tabs(["📅 Anual", "📆 Mensual", "📋 Detalle"])
    
    # --- TAB ANUAL ---
    with tab_anual:
        st.title("📅 Dashboard Anual")
        
        # Agregar por año
        df['anio'] = df['periodo'].str[:4]
        df_anual = df.groupby('anio').agg({
            'bruto': 'sum',
            'liquido': 'sum',
            'afp': 'sum',
            'salud': 'sum',
            'impuesto': 'sum',
            'cesantia': 'sum',
            'otros_descuentos': 'sum',
            'total_descuentos': 'sum'
        }).reset_index()
        
        # KPIs Anuales
        col1, col2, col3, col4 = st.columns(4)
        
        ultimo_anio = df_anual.iloc[-1]
        col1.metric("Bruto Anual", f"${ultimo_anio['bruto']:,.0f}")
        col2.metric("Líquido Anual", f"${ultimo_anio['liquido']:,.0f}")
        col3.metric("Descuentos Totales", f"${ultimo_anio['total_descuentos']:,.0f}")
        col4.metric("% Descuento", f"{(ultimo_anio['total_descuentos']/ultimo_anio['bruto']*100):.1f}%")
        
        st.divider()
        
        # Gráfico de barras: Bruto vs Líquido por año
        fig_anual = go.Figure()
        fig_anual.add_trace(go.Bar(
            name='Bruto',
            x=df_anual['anio'],
            y=df_anual['bruto'],
            marker_color='#3b82f6'
        ))
        fig_anual.add_trace(go.Bar(
            name='Líquido',
            x=df_anual['anio'],
            y=df_anual['liquido'],
            marker_color='#10b981'
        ))
        fig_anual.update_layout(
            title="Ingresos Anuales: Bruto vs Líquido",
            barmode='group',
            height=400
        )
        st.plotly_chart(fig_anual, use_container_width=True)
        
        # Descuentos anuales
        col1, col2 = st.columns(2)
        
        with col1:
            fig_desc_anual = px.bar(
                df_anual,
                x='anio',
                y=['afp', 'salud', 'impuesto', 'cesantia'],
                title="Descuentos Legales por Año",
                labels={'value': 'Monto ($)', 'variable': 'Tipo'},
                barmode='group'
            )
            st.plotly_chart(fig_desc_anual, use_container_width=True)
        
        with col2:
            # Tabla resumen anual
            st.subheader("Resumen Anual")
            st.dataframe(
                df_anual.style.format({
                    'bruto': '${:,.0f}',
                    'liquido': '${:,.0f}',
                    'afp': '${:,.0f}',
                    'salud': '${:,.0f}',
                    'impuesto': '${:,.0f}',
                    'total_descuentos': '${:,.0f}'
                }),
                use_container_width=True,
                height=400
            )
    
    # --- TAB MENSUAL ---
    with tab_mensual:
        st.title("📆 Dashboard Mensual")
        
        # Filtro de año
        anios_disponibles = sorted(df['anio'].unique())
        anio_seleccionado = st.selectbox(
            "Selecciona el año",
            anios_disponibles,
            index=len(anios_disponibles) - 1
        )
        
        df_anio = df[df['anio'] == anio_seleccionado].copy()
        
        # KPIs del año seleccionado
        st.subheader(f"Resumen {anio_seleccionado}")
        col1, col2, col3, col4 = st.columns(4)
        
        col1.metric("Bruto Acumulado", f"${df_anio['bruto'].sum():,.0f}")
        col2.metric("Líquido Acumulado", f"${df_anio['liquido'].sum():,.0f}")
        col3.metric("Promedio Mensual Líq.", f"${df_anio['liquido'].mean():,.0f}")
        col4.metric("Meses Registrados", len(df_anio))
        
        st.divider()
        
        # Evolución mensual
        fig_mensual = go.Figure()
        fig_mensual.add_trace(go.Scatter(
            x=df_anio['mes'],
            y=df_anio['bruto'],
            name='Bruto',
            mode='lines+markers',
            marker=dict(size=10),
            line=dict(width=3)
        ))
        fig_mensual.add_trace(go.Scatter(
            x=df_anio['mes'],
            y=df_anio['liquido'],
            name='Líquido',
            mode='lines+markers',
            marker=dict(size=10),
            line=dict(width=3)
        ))
        fig_mensual.update_layout(
            title=f"Evolución Mensual {anio_seleccionado}",
            height=400,
            hovermode='x unified'
        )
        st.plotly_chart(fig_mensual, use_container_width=True)
        
        # Descuentos mensuales
        col1, col2 = st.columns(2)
        
        with col1:
            fig_desc_mes = px.bar(
                df_anio,
                x='mes',
                y=['afp', 'salud', 'impuesto', 'cesantia'],
                title="Descuentos Legales por Mes",
                barmode='stack'
            )
            fig_desc_mes.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_desc_mes, use_container_width=True)
        
        with col2:
            # Top conceptos de "Otros Descuentos"
            st.subheader("Otros Descuentos")
            otros_items = []
            for liq in st.session_state.liquidaciones:
                if liq.periodo.startswith(anio_seleccionado):
                    for desc in liq.descuentos_items:
                        if desc.categoria == 'OTRO':
                            otros_items.append({
                                'Concepto': desc.nombre,
                                'Monto': desc.monto,
                                'Mes': liq.mes_nombre
                            })
            
            if otros_items:
                df_otros = pd.DataFrame(otros_items)
                top_otros = df_otros.groupby('Concepto')['Monto'].sum().sort_values(ascending=False).head(5)
                
                fig_otros = px.bar(
                    x=top_otros.values,
                    y=top_otros.index,
                    orientation='h',
                    title="Top 5 Otros Descuentos del Año"
                )
                st.plotly_chart(fig_otros, use_container_width=True)
            else:
                st.info("No hay otros descuentos en este año")
        
        # Tabla mensual
        st.subheader("Detalle Mensual")
        st.dataframe(
            df_anio[['mes', 'bruto', 'liquido', 'afp', 'salud', 'impuesto', 
                     'valor_hora_bruto', 'valor_hora_liquido']].style.format({
                'bruto': '${:,.0f}',
                'liquido': '${:,.0f}',
                'afp': '${:,.0f}',
                'salud': '${:,.0f}',
                'impuesto': '${:,.0f}',
                'valor_hora_bruto': '${:,.0f}',
                'valor_hora_liquido': '${:,.0f}'
            }),
            use_container_width=True
        )
    
    # --- TAB DETALLE ---
    with tab_detalle:
        st.title("📋 Detalle de Liquidaciones")
        
        # Selector de mes
        meses_disponibles = [(liq.periodo, liq.mes_nombre) for liq in st.session_state.liquidaciones]
        mes_seleccionado = st.selectbox(
            "Selecciona un mes",
            meses_disponibles,
            format_func=lambda x: x[1],
            index=len(meses_disponibles) - 1
        )
        
        liq = next(l for l in st.session_state.liquidaciones if l.periodo == mes_seleccionado[0])
        metricas_mes = calcular_metricas_mes(liq)
        
        # KPIs del mes
        st.subheader(f"Resumen de {liq.mes_nombre}")
        col1, col2, col3, col4 = st.columns(4)
        
        col1.metric("Bruto", f"${metricas_mes['bruto']:,.0f}")
        col2.metric("Líquido", f"${metricas_mes['liquido']:,.0f}")
        col3.metric("Valor Hora Bruto", f"${metricas_mes['valor_hora_bruto']:,.0f}")
        col4.metric("Valor Hora Líquido", f"${metricas_mes['valor_hora_liquido']:,.0f}")
        
        st.divider()
        
        # Información laboral
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📅 Información Laboral")
            st.write(f"**Días trabajados:** {liq.dias_trabajados}")
            st.write(f"**Días licencia:** {liq.dias_licencia}")
            st.write(f"**Días ausencia:** {liq.dias_ausencia}")
            st.write(f"**Días vacaciones:** {liq.dias_vacaciones}")
            st.write(f"**Horas base semanal:** {liq.horas_base_semanal}")
            st.write(f"**Sueldo base:** ${liq.sueldo_base:,}")
        
        with col2:
            st.subheader("💰 Totales")
            st.write(f"**Haberes Afectos:** ${liq.haberes_afectos_total:,}")
            st.write(f"**Haberes Exentos:** ${liq.haberes_exentos_total:,}")
            st.write(f"**Descuentos Legales:** ${liq.descuentos_legales_total:,}")
            st.write(f"**Otros Descuentos:** ${liq.otros_descuentos_total:,}")
            st.write(f"**Total Imponible:** ${liq.total_imponible:,}")
            st.write(f"**Total Tributable:** ${liq.total_tributable:,}")
        
        st.divider()
        
        # Detalle de haberes
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("💵 Haberes")
            haberes_data = [{
                'Concepto': h.nombre,
                'Tipo': 'Afecto' if h.tipo == 'haber_afecto' else 'Exento',
                'Monto': h.monto
            } for h in liq.haberes_items]
            
            if haberes_data:
                df_haberes = pd.DataFrame(haberes_data)
                st.dataframe(
                    df_haberes.style.format({'Monto': '${:,.0f}'}),
                    use_container_width=True,
                    height=300
                )
        
        with col2:
            st.subheader("💳 Descuentos")
            descuentos_data = [{
                'Concepto': d.nombre,
                'Categoría': d.categoria,
                'Monto': d.monto
            } for d in liq.descuentos_items]
            
            if descuentos_data:
                df_descuentos = pd.DataFrame(descuentos_data)
                st.dataframe(
                    df_descuentos.style.format({'Monto': '${:,.0f}'}),
                    use_container_width=True,
                    height=300
                )
        
        # Gráfico de composición
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Composición de descuentos
            desc_por_cat = df_descuentos.groupby('Categoría')['Monto'].sum()
            fig_desc_pie = px.pie(
                values=desc_por_cat.values,
                names=desc_por_cat.index,
                title="Composición de Descuentos"
            )
            st.plotly_chart(fig_desc_pie, use_container_width=True)
        
        with col2:
            # Desglose bruto vs descuentos vs líquido
            fig_waterfall = go.Figure(go.Waterfall(
                name="Flujo",
                orientation="v",
                measure=["absolute", "relative", "relative", "total"],
                x=["Bruto", "Desc. Legales", "Otros Desc.", "Líquido"],
                y=[metricas_mes['bruto'], 
                   -liq.descuentos_legales_total, 
                   -liq.otros_descuentos_total,
                   metricas_mes['liquido']],
                connector={"line": {"color": "rgb(63, 63, 63)"}},
            ))
            fig_waterfall.update_layout(title="De Bruto a Líquido", height=400)
            st.plotly_chart(fig_waterfall, use_container_width=True)

if __name__ == "__main__":
    main()
