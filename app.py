from datetime import date
import folium
from folium.plugins import MousePosition
import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(
    page_title="Plataforma de Aterrizaje Lunar - NASA", layout="wide"
)
st.title("🛰️ Evaluador de Sitios de Aterrizaje Lunar & Explorador Apollo")

# --- BARRA LATERAL: CONTROLES DE MISIÓN Y CAPAS ---
st.sidebar.header("1. Sitio Candidato a Evaluar")
nombre_sitio = st.sidebar.text_input(
    "Nombre del Sitio", value="Base Tranquilidad (Custom)"
)
latitud = st.sidebar.number_input(
    "Latitud Lunar (°)", min_value=-90.0, max_value=90.0, value=-3.01, step=0.05
)
longitud = st.sidebar.number_input(
    "Longitud Lunar (°)",
    min_value=-180.0,
    max_value=180.0,
    value=-23.42,
    step=0.05,
)

fecha_inicio = st.sidebar.date_input("Fecha de Inicio", value=date(2026, 1, 20))
fecha_fin = st.sidebar.date_input("Fecha de Fin", value=date(2026, 1, 25))

st.sidebar.divider()
st.sidebar.header("2. Referencia Histórica (Apollo)")
mostrar_apollo = st.sidebar.checkbox(
    "Mostrar Waypoints de Misión Apollo", value=True
)
mision_apollo = st.sidebar.selectbox(
    "Seleccionar Misión NASA Moon Trek",
    [
        "Apollo 11",
        "Apollo 12",
        "Apollo 14",
        "Apollo 15",
        "Apollo 16",
        "Apollo 17",
    ],
    disabled=not mostrar_apollo,
)
centrar_en = st.sidebar.radio(
    "Centrar mapa en:", ["Sitio Candidato", "Misión Apollo"], horizontal=True
)


# --- FUNCIONES DE CONSULTA A APIs DE LA NASA (CON CACHÉ) ---
@st.cache_data(ttl=3600)
def evaluar_sitio_lunar(nombre, lat, lon, f_inicio, f_fin):
  base_url = "https://ssd.jpl.nasa.gov/api/horizons.api"
  params_comunes = (
      "?format=json&MAKE_EPHEM=YES&EPHEM_TYPE=OBSERVER&CENTER='coord@301'"
      f"&COORD_TYPE=GEODETIC&SITE_COORD='{lon},{lat},0'"
      f"&START_TIME='{f_inicio}'&STOP_TIME='{f_fin}'&STEP_SIZE='1%20h'&QUANTITIES='4'"
  )

  def extraer_elevacion(texto):
    datos = []
    guardar = False
    for linea in texto.split("\n"):
      if "$$EOE" in linea:
        break
      if guardar and linea.strip():
        partes = linea.split()
        if len(partes) >= 4:
          try:
            grados = float(partes[3])
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
        "luz": extraer_elevacion(res_sol.get("result", "")),
        "comms": extraer_elevacion(res_tierra.get("result", "")),
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


# --- EJECUCIÓN DEL ANÁLISIS DE INGENIERÍA ---
if fecha_fin <= fecha_inicio:
  st.error("La fecha de fin debe ser posterior a la fecha de inicio.")
  st.stop()

with st.spinner(
    f"Consultando efemérides NASA JPL Horizons para {nombre_sitio}..."
):
  datos_mision = evaluar_sitio_lunar(
      nombre_sitio, latitud, longitud, str(fecha_inicio), str(fecha_fin)
  )

if "error" in datos_mision:
  st.error(f"Error consultando la API de NASA Horizons: {datos_mision['error']}")
  st.stop()

# Cálculos de tu analizador de ingeniería
horas_totales = len(datos_mision["luz"])
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

# Veredicto automático
if perdidas_senal == horas_totales:
  estado_veredicto = "RECHAZADO"
  mensaje_veredicto = (
      "RECHAZADO: Zona de sombra de radio. La Tierra no es visible a un grado"
      " seguro (<10°)."
  )
  color_pin = "red"
  st.error(f"🚨 **{mensaje_veredicto}**")
elif horas_ideales_aterrizaje == 0:
  estado_veredicto = "MARGINAL"
  mensaje_veredicto = (
      "MARGINAL: No hay ventanas de luz rasante (5°–20°) en este periodo."
      " Aterrizaje a ciegas o con sobrecalentamiento."
  )
  color_pin = "orange"
  st.warning(f"⚠️ **{mensaje_veredicto}**")
elif horas_peligro_termico > (horas_totales / 2):
  estado_veredicto = "ADVERTENCIA"
  mensaje_veredicto = (
      "ADVERTENCIA: Alto riesgo térmico (>70°). La mayor parte de la misión"
      " transcurrirá bajo luz solar extrema."
  )
  color_pin = "orange"
  st.warning(f"🔥 **{mensaje_veredicto}**")
else:
  estado_veredicto = "VIABLE"
  mensaje_veredicto = (
      f"SITIO VIABLE: Se encontraron {horas_ideales_aterrizaje} horas de"
      " iluminación ideal (5°–20°) para el descenso. Conexión con Tierra"
      " aceptable."
  )
  color_pin = "green"
  st.success(f"✅ **{mensaje_veredicto}**")

# --- MÉTRICAS CLAVE ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Veredicto Ingeniería", estado_veredicto)
c2.metric(
    "Luz Rasante Ideal (5°–20°)",
    f"{horas_ideales_aterrizaje} h / {horas_totales} h",
)
c3.metric("Peligro Térmico (>70°)", f"{horas_peligro_termico} h")
c4.metric("Riesgo Pérdida Señal (<10°)", f"{perdidas_senal} h")

# --- CARGA DE DATOS APOLLO ---
df_apollo = (
    cargar_waypoints_apollo(mision_apollo) if mostrar_apollo else pd.DataFrame()
)

# Determinar centro inicial del mapa
if (
    centrar_en == "Misión Apollo"
    and not df_apollo.empty
    and "x" in df_apollo.columns
):
  centro_mapa = [df_apollo["y"].mean(), df_apollo["x"].mean()]
  zoom_inicial = 6
else:
  centro_mapa = [latitud, longitud]
  zoom_inicial = 5

# --- CONSTRUCCIÓN DEL MAPA LUNAR (NASA MOON TREK EPSG4326) ---
mapa = folium.Map(
    location=centro_mapa,
    zoom_start=zoom_inicial,
    crs="EPSG4326",
    tiles=None,
    control_scale=True,
)

# Capa 1: Mapa Base Global LRO WAC
folium.TileLayer(
    tiles="https://trek.nasa.gov/tiles/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
    attr="NASA / LRO WAC",
    name="Superficie Lunar Global (LRO WAC)",
    max_zoom=20,
    max_native_zoom=9,
    overlay=False,
).add_to(mapa)

# Capa 2: Parche Ultra Alta Resolución Apollo 11 (26cm/px)
folium.TileLayer(
    tiles="https://trek.nasa.gov/tiles/Moon/EQ/apollo11_26cm_mosaic_byte_geo_1_2_highContrast/1.0.0/default/default028mm/{z}/{y}/{x}.png",
    attr="NASA / LROC / Apollo 11",
    name="Apollo 11 Ultra Resolución (26cm)",
    max_zoom=20,
    max_native_zoom=8,
    overlay=True,
).add_to(mapa)

# Marcador del Sitio Candidato Evaluado
folium.Marker(
    location=[latitud, longitud],
    popup=(
        f"<b>{nombre_sitio}</b><br>Estado: {estado_veredicto}<br>Luz ideal:"
        f" {horas_ideales_aterrizaje}h<br>Peligro térmico:"
        f" {horas_peligro_termico}h"
    ),
    tooltip=f"🎯 {nombre_sitio} ({estado_veredicto})",
    icon=folium.Icon(color=color_pin, icon="rocket", prefix="fa"),
).add_to(mapa)

# Marcadores de los Waypoints de la Misión Apollo seleccionada
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
        icon=folium.Icon(color="blue", icon="flag", prefix="fa"),
    ).add_to(grupo_apollo)
  grupo_apollo.add_to(mapa)

folium.LayerControl(collapsed=False).add_to(mapa)
MousePosition(
    position="bottomleft", separator=" | Lon: ", prefix="Lat: "
).add_to(mapa)

# --- RENDERIZAR MAPA Y CAPTURAR CLIC ---
st.caption(
    "💡 Haz clic en cualquier punto de la Luna para obtener sus coordenadas o"
    " activa las capas de resolución en la esquina superior derecha del mapa."
)
mapa_data = st_folium(mapa, width=1200, height=550)

if mapa_data and mapa_data.get("last_clicked"):
  c_lat = mapa_data["last_clicked"]["lat"]
  c_lon = mapa_data["last_clicked"]["lng"]
  st.info(
      f"📍 Coordenadas seleccionadas con clic: **Latitud = {c_lat:.4f}° ,"
      f" Longitud = {c_lon:.4f}°** (cópialas en el menú izquierdo para correr"
      " el análisis de ingeniería en ese punto)."
  )

# --- TABLA DE DATOS DE LA MISIÓN APOLLO ---
if mostrar_apollo and not df_apollo.empty:
  with st.expander(
      f"📋 Ver tabla de elementos registrados en {mision_apollo}"
      f" ({len(df_apollo)} puntos)"
  ):
    columnas_mostrar = [
        col
        for col in ["FID", "name", "x", "y", "elevation", "template"]
        if col in df_apollo.columns
    ]
    st.dataframe(df_apollo[columnas_mostrar], use_container_width=True)
