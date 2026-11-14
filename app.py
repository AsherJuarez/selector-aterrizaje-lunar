from datetime import date
import os
import folium
import matplotlib.pyplot as plt
import rasterio
from rasterio.plot import show
from rasterio.warp import transform
import requests
import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(page_title="Evaluador de Aterrizaje Lunar", layout="wide")
st.title("🛰️ Evaluador de Viabilidad de Aterrizaje Lunar (NASA Horizons)")

# --- BARRA LATERAL: CONTROLES DEL USUARIO ---
st.sidebar.header("Parámetros de la Misión")
nombre_sitio = st.sidebar.text_input(
    "Nombre del Sitio", value="Base Tranquilidad (Custom)"
)
latitud = st.sidebar.number_input(
    "Latitud Lunar (°)", min_value=-90.0, max_value=90.0, value=-3.01, step=0.1
)
longitud = st.sidebar.number_input(
    "Longitud Lunar (°)",
    min_value=-180.0,
    max_value=180.0,
    value=-23.42,
    step=0.1,
)

fecha_inicio = st.sidebar.date_input("Fecha de Inicio", value=date(2026, 1, 20))
fecha_fin = st.sidebar.date_input("Fecha de Fin", value=date(2026, 1, 25))

st.sidebar.divider()
req_luz_min = st.sidebar.slider("Mínimo de horas de luz requeridas", 0, 120, 24)
req_comms_min = st.sidebar.slider(
    "Mínimo de horas de comunicación requeridas", 0, 120, 24
)


# --- FUNCIÓN DE CONSULTA A NASA JPL HORIZONS ---
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
            datos.append({
                "fecha_hora": f"{partes[0]} {partes[1]}",
                "elev": float(partes[3]),
                "visible": float(partes[3]) > 0,
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


# --- EJECUCIÓN DEL ANÁLISIS ---
if fecha_fin <= fecha_inicio:
  st.error("La fecha de fin debe ser posterior a la fecha de inicio.")
else:
  with st.spinner(
      f"Consultando efemérides de la NASA para {nombre_sitio}..."
  ):
    datos_mision = evaluar_sitio_lunar(
        nombre_sitio, latitud, longitud, str(fecha_inicio), str(fecha_fin)
    )

  if "error" in datos_mision:
    st.error(
        f"Error consultando la API de NASA Horizons: {datos_mision['error']}"
    )
  else:
    horas_luz = sum(1 for x in datos_mision["luz"] if x["visible"])
    horas_comms = sum(1 for x in datos_mision["comms"] if x["visible"])
    total_horas = len(datos_mision["luz"])

    es_apto = (horas_luz >= req_luz_min) and (horas_comms >= req_comms_min)

    # --- TARJETAS DE RESULTADOS ---
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Estado del Sitio", "APTO ✅" if es_apto else "NO APTO ❌")
    col_m2.metric("Horas con Luz Solar", f"{horas_luz} h / {total_horas} h")
    col_m3.metric(
        "Horas con Señal a Tierra", f"{horas_comms} h / {total_horas} h"
    )
    col_m4.metric("Coordenadas", f"{latitud:.2f}°, {longitud:.2f}°")

    # --- PESTAÑAS DE VISUALIZACIÓN ---
    tab1, tab2 = st.tabs(
        ["🌍 Mapa Interactivo (Zoom y Clic)", "🛰️ Proyección Raster LROC"]
    )

    with tab1:
      m = folium.Map(
          location=[latitud, longitud], zoom_start=4, tiles=None, crs="EPSG4326"
      )
      folium.WmsTileLayer(
          url="https://planetarymaps.usgs.gov/cgi-bin/mapserv?map=/maps/earth/moon_simp_cyl.map",
          layers="LROC_WAC",
          fmt="image/png",
          transparent=False,
          name="Superficie Lunar (LROC WAC)",
          attr="NASA / GSFC / ASU",
      ).add_to(m)

      color_marcador = "green" if es_apto else "red"
      folium.Marker(
          location=[latitud, longitud],
          popup=(
              f"<b>{nombre_sitio}</b><br>Luz: {horas_luz}h<br>Comms:"
              f" {horas_comms}h"
          ),
          tooltip=nombre_sitio,
          icon=folium.Icon(color=color_marcador, icon="rocket", prefix="fa"),
      ).add_to(m)

      st.caption(
          "💡 Tip: Puedes hacer clic en cualquier punto del mapa para ver sus"
          " coordenadas exactas."
      )
      mapa_clic = st_folium(m, width=1100, height=500)

      if mapa_clic and mapa_clic.get("last_clicked"):
        c_lat = mapa_clic["last_clicked"]["lat"]
        c_lon = mapa_clic["last_clicked"]["lng"]
        st.info(
            f"📍 Punto seleccionado en el mapa: **Latitud {c_lat:.4f}°,"
            f" Longitud {c_lon:.4f}°** (ingresa estos valores en el panel"
            " izquierdo para evaluarlo)."
        )

    with tab2:
      if os.path.exists("quickmap-lroc.vrt"):
        try:
          with rasterio.open("quickmap-lroc.vrt") as mapa_lunar:
            fig, ax = plt.subplots(figsize=(10, 6))
            show(mapa_lunar, ax=ax, cmap="gray")

            crs_origen = {"proj": "longlat", "a": 1737400, "b": 1737400}
            x_mapa, y_mapa = transform(
                crs_origen,
                mapa_lunar.crs,
                [datos_mision["lon"]],
                [datos_mision["lat"]],
            )
            x_final, y_final = x_mapa[0], y_mapa[0]

            color_punto = "#00ff00" if es_apto else "#ff3333"
            ax.plot(
                x_final,
                y_final,
                marker="o",
                color=color_punto,
                markersize=12,
                markeredgecolor="black",
                markeredgewidth=2,
            )
            ax.text(
                x_final + 50000,
                y_final,
                nombre_sitio,
                color="white",
                fontsize=11,
                fontweight="bold",
                bbox=dict(facecolor="black", alpha=0.7, edgecolor="none"),
            )
            ax.set_title(
                f"Misión: {nombre_sitio} | Luz: {horas_luz}h | Comms:"
                f" {horas_comms}h"
            )
            st.pyplot(fig)
        except Exception as e:
          st.warning(f"No se pudo renderizar el archivo VRT: {e}")
      else:
        st.info(
            "Para ver esta proyección local, sube el archivo"
            " `quickmap-lroc.vrt` a tu repositorio de GitHub."
        )
