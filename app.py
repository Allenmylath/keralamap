import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Point

# ── Config ────────────────────────────────────────────────────────────────────

GEOJSON_PATH = "data/villages.geojson"   # 🔧 Replace with your actual path
VILLAGE_NAME_FIELD = None                # 🔧 Set to field name e.g. "NAME_3", or leave None to auto-detect

MAP_CENTER = [10.8505, 76.2711]          # Kerala center — adjust to your region
MAP_ZOOM = 8

HIGHLIGHT_COLOR = "#FF5733"
DEFAULT_FILL_COLOR = "#3186cc"

# ── Load GeoJSON ──────────────────────────────────────────────────────────────

@st.cache_data
def load_geodata(path: str):
    gdf = gpd.read_file(path)
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    return gdf

def detect_name_field(gdf: gpd.GeoDataFrame) -> str:
    """Pick the first string column that likely holds a place name."""
    if VILLAGE_NAME_FIELD and VILLAGE_NAME_FIELD in gdf.columns:
        return VILLAGE_NAME_FIELD
    candidates = [c for c in gdf.columns if c.lower() not in ("geometry",)
                  and gdf[c].dtype == object]
    return candidates[0] if candidates else None

# ── Point-in-polygon lookup ───────────────────────────────────────────────────

def find_village(gdf: gpd.GeoDataFrame, lat: float, lon: float, name_field: str):
    pt = Point(lon, lat)   # Shapely uses (x=lon, y=lat)
    for _, row in gdf.iterrows():
        if row.geometry and row.geometry.contains(pt):
            return row[name_field] if name_field else "Unknown", row.geometry
    return None, None

# ── Build base map ────────────────────────────────────────────────────────────

def build_map(gdf: gpd.GeoDataFrame, name_field: str, clicked_village: str = None):
    m = folium.Map(location=MAP_CENTER, zoom_start=MAP_ZOOM, tiles="CartoDB positron")

    def style_fn(feature):
        village = feature["properties"].get(name_field, "")
        is_selected = village == clicked_village and clicked_village is not None
        return {
            "fillColor": HIGHLIGHT_COLOR if is_selected else DEFAULT_FILL_COLOR,
            "color": "white",
            "weight": 0.5,
            "fillOpacity": 0.6 if is_selected else 0.3,
        }

    folium.GeoJson(
        data=gdf.__geo_interface__,
        name="Villages",
        style_function=style_fn,
        highlight_function=lambda _: {
            "fillColor": "#ffff00",
            "color": "white",
            "weight": 1.5,
            "fillOpacity": 0.7,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=[name_field] if name_field else [],
            aliases=["Village:"] if name_field else [],
            sticky=False,
        ),
    ).add_to(m)

    return m

# ── Main app ──────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Village Map", layout="wide")
st.title("🗺️ Village Map")
st.caption("Click anywhere on the map to identify the village.")

# Load data
try:
    gdf = load_geodata(GEOJSON_PATH)
except Exception as e:
    st.error(f"Failed to load GeoJSON from `{GEOJSON_PATH}`: {e}")
    st.stop()

name_field = detect_name_field(gdf)
if not name_field:
    st.warning("No suitable name field detected in GeoJSON properties.")

# Session state for clicked village
if "clicked_village" not in st.session_state:
    st.session_state.clicked_village = None
if "clicked_coords" not in st.session_state:
    st.session_state.clicked_coords = None

# Build and render map
m = build_map(gdf, name_field, st.session_state.clicked_village)

# Add marker for last click
if st.session_state.clicked_coords:
    lat, lon = st.session_state.clicked_coords
    village = st.session_state.clicked_village or "No village found"
    folium.Marker(
        location=[lat, lon],
        popup=folium.Popup(f"<b>{village}</b>", max_width=200),
        tooltip="Click result",
        icon=folium.Icon(color="red", icon="info-sign"),
    ).add_to(m)

map_data = st_folium(m, width="100%", height=600, returned_objects=["last_clicked"])

# Handle click
if map_data and map_data.get("last_clicked"):
    lat = map_data["last_clicked"]["lat"]
    lon = map_data["last_clicked"]["lng"]

    if (lat, lon) != st.session_state.clicked_coords:
        st.session_state.clicked_coords = (lat, lon)
        village_name, _ = find_village(gdf, lat, lon, name_field)
        st.session_state.clicked_village = village_name
        st.rerun()

# Info panel below map
st.divider()
if st.session_state.clicked_village:
    st.success(f"📍 **Village:** {st.session_state.clicked_village}")
elif st.session_state.clicked_coords:
    lat, lon = st.session_state.clicked_coords
    st.warning(f"No village polygon found at ({lat:.5f}, {lon:.5f})")
else:
    st.info("Click on the map to identify a village.")
