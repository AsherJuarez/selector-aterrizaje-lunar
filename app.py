from datetime import date
import folium
from folium.plugins import MousePosition
import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(
    page_title="Simulador de Aterrizaje Lunar - NASA", layout="wide"
)
st.title("🛰️ Simulador de Aterrizaje Lunar & Explorador Apollo")

# --- DICCIONARIO DE CAPAS DE ALTA RESOLUCIÓN POR MISIÓN ---
CAPAS_ALTA_RES = {
    "Apollo 11": {
        "nombre": "Apollo 11 Ultra Res (26cm)",
        "url": "https://trek.nasa.gov/tiles/Moon/EQ/apollo11_26cm_mosaic_byte_geo_1_2_highContrast/1.0.0/default/default028mm/{z}/{y}/{x}.png",
        "max_native_zoom": 16,
    },
    "Apollo 12": {
        "nombre": "Apollo 12 Alta Res (60x60km)",
        "url": "https://trek.nasa.gov/tiles/Moon/EQ/A12_60x60km.0_3.eq/1.0.0/default/default028mm/{z}/{y}/{x}.png",
        "max_native_zoom": 14,
    },
    "Apollo 14": {
        "nombre": "Apollo 14 Alta Res (60x60km)",
        "url": "https://trek.nasa.gov/tiles/Moon/EQ/A14_60x60km.0_3.eq/1.0.0/default/default028mm/{z}/{y}/{x}.png",
        "max_native_zoom": 14,
    },
    "Apollo 15": {
        "nombre": "Apollo 15 Alta Res (60x60km)",
        "url": "https://trek.nasa.gov/tiles/Moon/EQ/A15_60x60km.0_3.eq/1.0.0/default/default028mm/{z}/{y}/{x}.png",
        "max_native_zoom": 14,
    },
    "Apollo 16": {
        "nombre": "Apollo 16 Alta Res (60x60km)",
        "url": "https://trek.nasa.gov/tiles/Moon/EQ/A16_60x60km.0_3.eq/1.0.0/default/default028mm/{z}/{y}/{x}.png",
        "max_native_zoom": 14,
    },
    "Apollo 17": {
        "nombre": "Apollo 17 Alta Res (60x60km)",
        "url": "https://trek.nasa.gov/tiles/Moon/EQ/A17_60x60km.0_3.eq/1.0.0/default/default028mm/{z}/{y}/{x}.png",
        "max_native_zoom": 14,
    },
}

# --- BARRA LATERAL: PARÁMETROS DEL SITIO Y CAPAS ---
st.sidebar.header("1. Parámetros del Sitio de Aterrizaje")
nombre_sitio = st.sidebar.text_input("Nombre del Sitio", value="Custom")
latitud = st.sidebar.number_input(
    "Latitud Lunar (°)", min_value=-90.0, max_value=90.0, value=23.25, step=0.05
)
longitud = st.sidebar.number_input(
    "Longitud Lunar (°)",
    min_value=-180.0,
    max_value=180.0,
    value=26.45,
    step=0.05,
)

fecha_inicio = st.sidebar.date_input("Fecha de Inicio", value=date(2026, 4, 22))
fecha_fin = st.sidebar.date_input("Fecha de Fin", value=date(2026, 4, 23))

st.sidebar.divider()
st.sidebar.header("2. Explorador Misiones Apollo")
mostrar_apollo = st.sidebar.checkbox(
    "Mostrar Waypoints y Capa Alta Res Apollo", value=True
)
mision_apollo = st.sidebar.selectbox(
    "Seleccionar Misión NASA Moon Trek",
    list(CAPAS_ALTA_RES.keys()),
    disabled=not mostrar_apollo,
)
centrar_en = st.sidebar.radio(
    "Centrar mapa en:", ["Sitio Candidato", "Misión Apollo"], horizontal=True
)
nivel_zoom = st.sidebar.slider("Nivel de Zoom inicial", 2, 18, 8)


# --- 1. FUNCIONES BASE (Extracción con índice [-1]) ---
def extraer_elevacion_y_grados(texto):
  datos = []
  guardar = False
  for linea in texto.split("\n"):
    if "$$EOE" in linea:
      break
    if guardar and linea.strip():
      partes = linea.split()
      if len(partes) >= 4:
        try:
          grados = float(partes[-1])
          datos.append({
              "fecha_hora": f"{partes[0]} {partes[1]}",
              "grados": grados,
              "visible": grados > 0,
          })
        except ValueError:
          pass
    if "$$SOE" in linea:
      guardar = True
  return datos


@st.cache_data(ttl=3600)
def evaluar_sitio_lunar(nombre, lat, lon, f_inicio, f_fin):
  base_url = "https://ssd.jpl.nasa.gov/api/horizons.api"
  params_comunes = (
      "?format=json&MAKE_EPHEM=YES&EPHEM_TYPE=OBSERVER&CENTER='coord@301'"
      f"&COORD_TYPE=GEODETIC&SITE_COORD='{lon},{lat},0'"
      f"&START_TIME='{f_inicio}'&STOP_TIME='{f_fin}'&STEP_SIZE='1%20h'&QUANTITIES='4'"
  )
  try:
    res_sol = requests.get(
        base_url + params_comunes + "&COMMAND='10'", timeout=15
    ).json()
    res_tierra = requests.get(
        base_url + params_comunes + "&COMMAND='399'", timeout=15
    ).json()
    return {
        "sitio": nombre,
        "lat": lat,
        "lon": lon,
        "luz": extraer_elevacion_y_grados(res_sol.get("result", "")),
        "comms": extraer_elevacion_y_grados(res_tierra.get("result", "")),
    }
  except Exception as e:
    return {"error": str(e)}


@st.cache_data(ttl=86400)
def cargar_waypoints_apollo(mision):
  urls_apollo = {
      "Apollo 11": "https://trek.nasa.gov/moon/trekarcgis/rest/services/Apollo11_waypoints/MapServer/0/query?f=json&where=1%3D1&returnGeometry=true&outFields=*&outSR=104903",
      "Apollo 12": "https://trek.nasa.gov/moon/trekarcgis/rest/services/Apollo12_waypoints/MapServer/0/query?f=json&where=1%3D1&returnGeometry=true&outFields=*&outSR=104903",
      "Apollo 14": "https://trek.nasa.gov/moon/trekarcgis/rest/services/Apollo14_waypoints/MapServer/0/query?f=json&where=1%3D1&returnGeometry=true&outFields=*&outSR=104903",
      "Apollo 15": "https://trek.nasa.gov/moon/trekarcgis/rest/services/Apollo15_waypoints/MapServer/0/query?f=json&where=1%3D1&returnGeometry=true&outFields=*&outSR=104903",
      "Apollo 16": "https://trek.nasa.gov/moon/trekarcgis/rest/services/Apollo16_waypoints/MapServer/0/query?f=json&where=1%3D1&returnGeometry=true&outFields=*&outSR=104903",
      "Apollo 17": "https://trek.nasa.gov/moon/trekarcgis2/rest/services/Apollo17_waypoints/MapServer/0/query?f=json&where=1%3D1&returnGeometry=true&outFields=*&outSR=104903",
  }
  try:
    res = requests.get(urls_apollo[mision], timeout=12)
    if res.status_code == 200:
      datos = res.json()
      filas = []
      for feat in datos.get("features", []):
        attr = feat.get("attributes", {})
        geom = feat.get("geometry", {})
        filas.append({**attr, **geom})
      return pd.DataFrame(filas)
  except Exception:
    pass
  return pd.DataFrame()


# --- 2. EJECUCIÓN Y EXTRACCIÓN DE DATOS ---
if fecha_fin <= fecha_inicio:
  st.error("La fecha de fin debe ser posterior a la fecha de inicio.")
  st.stop()

with st.spinner(f"Obteniendo telemetría de la NASA para: {nombre_sitio}..."):
  datos_mision = evaluar_sitio_lunar(
      nombre_sitio, latitud, longitud, str(fecha_inicio), str(fecha_fin)
  )

if "error" in datos_mision:
  st.error(f"Error consultando la API de NASA Horizons: {datos_mision['error']}")
  st.stop()

horas_totales = len(datos_mision["luz"])

if horas_totales == 0:
  st.error(
      "ERROR: La API no devolvió datos. Revisa el formato o rango de tus"
      " fechas."
  )
  st.stop()

# --- 3. MOTOR DE ANÁLISIS DE INGENIERÍA ---
horas_luz = sum(1 for x in datos_mision["luz"] if x["visible"])
horas_comms = sum(1 for x in datos_mision["comms"] if x["visible"])

horas_ideales_aterrizaje = 0
horas_peligro_termico = 0
perdidas_senal = 0

for i in range(horas_totales):
  sol_grados = datos_mision["luz"][i]["grados"]
  tierra_grados = datos_mision["comms"][i]["grados"]

  if 5 <= sol_grados <= 20:
    horas_ideales_aterrizaje += 1
  if sol_grados > 70:
    horas_peligro_termico += 1
  if tierra_grados < 10:
    perdidas_senal += 1

# Reporte de Viabilidad de Ingeniería
st.subheader("📋 Reporte de Viabilidad de Ingeniería")

if perdidas_senal == horas_totales:
  estado_veredicto = "RECHAZADO"
  color_pin = "red"
  st.error(
      "🚨 **RECHAZADO:** Zona de sombra de radio. La Tierra no es visible a un"
      " grado seguro (<10°)."
  )
elif horas_ideales_aterrizaje == 0:
  estado_veredicto = "MARGINAL"
  color_pin = "orange"
  st.warning(
      "⚠️ **MARGINAL:** No hay ventanas de luz rasante (5°–20°) en este"
      " periodo. Aterrizaje a ciegas o con sobrecalentamiento."
  )
elif horas_peligro_termico > (horas_totales / 2):
  estado_veredicto = "ADVERTENCIA"
  color_pin = "orange"
  st.warning(
      "🔥 **ADVERTENCIA:** Alto riesgo térmico (>70°). La mayor parte de la"
      " misión transcurrirá bajo luz solar extrema."
  )
else:
  estado_veredicto = "VIABLE"
  color_pin = "green"
  st.success(
      f"✅ **SITIO VIABLE:** Se encontraron **{horas_ideales_aterrizaje}"
      " horas** de iluminación ideal (sombras largas, 5°–20°) para el"
      " descenso. Calidad de conexión con Tierra: Aceptable (evitando el"
      " horizonte montañoso)."
  )

# Tarjetas con métricas exactas de telemetría
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Estado", estado_veredicto)
m2.metric("Ventana Total", f"{horas_totales} h")
m3.metric("Luz Solar Directa", f"{horas_luz} h")
m4.metric("Señal a la Tierra", f"{horas_comms} h")
m5.metric("Luz Ideal (5°–20°)", f"{horas_ideales_aterrizaje} h")

# --- 4. VISUALIZACIÓN CARTOGRÁFICA ---
df_apollo = (
    cargar_waypoints_apollo(mision_apollo) if mostrar_apollo else pd.DataFrame()
)

if (
    centrar_en == "Misión Apollo"
    and not df_apollo.empty
    and "x" in df_apollo.columns
):
  centro_mapa = [df_apollo["y"].mean(), df_apollo["x"].mean()]
else:
  centro_mapa = [latitud, longitud]

mapa = folium.Map(
    location=centro_mapa,
    zoom_start=nivel_zoom,
    crs="EPSG4326",
    tiles=None,
    control_scale=True,
)

# Capa 1: Mapa Base Global de la NASA (LRO WAC)
folium.TileLayer(
    tiles="https://trek.nasa.gov/tiles/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
    attr="NASA / LRO WAC Global",
    name="Superficie Lunar Global (Base)",
    max_zoom=20,
    max_native_zoom=7,
    overlay=False,
).add_to(mapa)

# Capa 2: Parche dinámico de Alta Resolución de la misión Apollo seleccionada
if mostrar_apollo and mision_apollo in CAPAS_ALTA_RES:
  info_capa = CAPAS_ALTA_RES[mision_apollo]
  folium.TileLayer(
      tiles=info_capa["url"],
      attr=f"NASA / LROC / {mision_apollo}",
      name=info_capa["nombre"],
      max_zoom=20,
      max_native_zoom=info_capa["max_native_zoom"],
      overlay=True,
  ).add_to(mapa)

# Marcador del Sitio Evaluado
folium.Marker(
    location=[latitud, longitud],
    popup=(
        f"<b>{nombre_sitio}</b><br>"
        f"Veredicto: {estado_veredicto}<br>"
        f"Luz directa: {horas_luz}h / {horas_totales}h<br>"
        f"Señal Tierra: {horas_comms}h / {horas_totales}h<br>"
        f"Luz ideal descenso: {horas_ideales_aterrizaje}h"
    ),
    tooltip=f"🎯 {nombre_sitio} ({estado_veredicto})",
    icon=folium.Icon(color=color_pin, icon="rocket", prefix="fa"),
).add_to(mapa)

# Marcadores de Waypoints de la Misión Apollo seleccionada
if (
    mostrar_apollo
    and not df_apollo.empty
    and "x" in df_apollo.columns
    and "y" in df_apollo.columns
):
  grupo_apollo = folium.FeatureGroup(name=f"Waypoints {mision_apollo}")
  for _, row in df_apollo.iterrows():
    nombre_wp = row.get("name", f"Punto {row.get('FID', '')}")
    link_info = row.get("template", "")
    html_popup = f"""
        <div style="font-family: Arial; min-width: 160px;">
            <b>{mision_apollo}: {nombre_wp}</b><br>
            <hr style="margin: 4px 0;">
            <b>Lat:</b> {row['y']:.5f}°<br>
            <b>Lon:</b> {row['x']:.5f}°<br>
            {f'<a href="{link_info}" target="_blank">Ficha NASA</a>' if link_info else ''}
        </div>
        """
    folium.Marker(
        location=[row["y"], row["x"]],
        popup=folium.Popup(html_popup, max_width=250),
        tooltip=f"{mision_apollo}: {nombre_wp}",
        icon=folium.Icon(color="red", icon="info-sign"),
    ).add_to(grupo_apollo)
  grupo_apollo.add_to(mapa)

folium.LayerControl(collapsed=False).add_to(mapa)
MousePosition(
    position="bottomleft", separator=" | Lon: ", prefix="Lat: "
).add_to(mapa)

st.caption(
    "💡 Haz clic en cualquier punto del mapa lunar para ver sus coordenadas o"
    " activa las capas de resolución en la esquina superior derecha."
)
mapa_data = st_folium(mapa, width=1200, height=550)

if mapa_data and mapa_data.get("last_clicked"):
  c_lat = mapa_data["last_clicked"]["lat"]
  c_lon = mapa_data["last_clicked"]["lng"]
  st.info(
      f"📍 Coordenadas seleccionadas con clic: **Latitud = {c_lat:.4f}° ,"
      f" Longitud = {c_lon:.4f}°** (cópialas en el panel izquierdo para"
      " evaluarlas)."
  )

# --- TABLA DE DATOS DE LA MISIÓN APOLLO ---
if mostrar_apollo and not df_apollo.empty:
  with st.expander(
      f"📋 Elementos registrados en el sitio de {mision_apollo}"
      f" ({len(df_apollo)} puntos)"
  ):
    columnas_mostrar = [
        col
        for col in ["FID", "name", "x", "y", "elevation", "template"]
        if col in df_apollo.columns
    ]
    st.dataframe(df_apollo[columnas_mostrar], use_container_width=True)
