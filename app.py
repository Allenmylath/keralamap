import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Point

# ── Config ────────────────────────────────────────────────────────────────────

GEOJSON_PATH = "village.geojson"         # same folder as this script
VILLAGE_NAME_FIELD = "NAME"

MAP_CENTER = [10.8505, 76.2711]          # adjust to your region
MAP_ZOOM = 8

HIGHLIGHT_COLOR = "#FF5733"
DEFAULT_FILL_COLOR = "#3186cc"

# ── Load GeoJSON (cached) ─────────────────────────────────────────────────────

@st.cache_data
def load_geodata(path: str):
    gdf = gpd.read_file(path)
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    gdf = gdf[gdf.geometry.notna()].reset_index(drop=True)
    return gdf

def detect_name_field(gdf: gpd.GeoDataFrame) -> str:
    if VILLAGE_NAME_FIELD and VILLAGE_NAME_FIELD in gdf.columns:
        return VILLAGE_NAME_FIELD
    candidates = [
        c for c in gdf.columns
        if c.lower() != "geometry" and gdf[c].dtype == object
    ]
    return candidates[0] if candidates else None

# ── Fast point-in-polygon using spatial index ─────────────────────────────────

def find_village(gdf: gpd.GeoDataFrame, lat: float, lon: float, name_field: str):
    pt = Point(lon, lat)
    # R-tree narrows to bounding-box candidates first, then exact check
    possible_idx = list(gdf.sindex.intersection(pt.bounds))
    for i in possible_idx:
        row = gdf.iloc[i]
        if row.geometry.contains(pt):
            return row[name_field] if name_field else "Unknown"
    return None

# ── Base map ──────────────────────────────────────────────────────────────────

def build_base_map(geojson_str: str, name_field: str, clicked_village: str):
    import json
    m = folium.Map(location=MAP_CENTER, zoom_start=MAP_ZOOM, tiles="CartoDB positron")

    def style_fn(feature):
        is_selected = (
            clicked_village is not None
            and feature["properties"].get(name_field) == clicked_village
        )
        return {
            "fillColor": HIGHLIGHT_COLOR if is_selected else DEFAULT_FILL_COLOR,
            "color": "white",
            "weight": 0.5,
            "fillOpacity": 0.65 if is_selected else 0.3,
        }

    folium.GeoJson(
        data=json.loads(geojson_str),
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

    # ✅ Key fix: ensures last_clicked fires even when GeoJson layer absorbs the click
    # CSS hides the visible coordinate popup while keeping click detection working
    folium.LatLngPopup().add_to(m)
    hide_popup_css = """
    <style>
    .leaflet-popup-content-wrapper { display: none !important; }
    .leaflet-popup-tip-container    { display: none !important; }
    </style>
    """
    m.get_root().html.add_child(folium.Element(hide_popup_css))

    return m

# ── Main app ──────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Village Map", layout="wide")
st.title("🗺️ Village Map")
st.caption("Click anywhere on the map to identify the village.")

# Load data
try:
    gdf = load_geodata(GEOJSON_PATH)
except Exception as e:
    st.error(f"Could not load `{GEOJSON_PATH}`: {e}")
    st.stop()

name_field = detect_name_field(gdf)
if not name_field:
    st.warning("No name field found in GeoJSON properties.")

# Session state
if "clicked_village" not in st.session_state:
    st.session_state.clicked_village = None
if "clicked_coords" not in st.session_state:
    st.session_state.clicked_coords = None

# Serialize once — passed to cached map builder
geojson_str = gdf.to_json()

# Build base map (cached per unique clicked_village value)
m = build_base_map(geojson_str, name_field, st.session_state.clicked_village)

# Add result marker (cheap, outside cache)
if st.session_state.clicked_coords:
    lat, lon = st.session_state.clicked_coords
    label = st.session_state.clicked_village or "No village found"
    folium.Marker(
        location=[lat, lon],
        popup=folium.Popup(f"<b>{label}</b>", max_width=220),
        tooltip=label,
        icon=folium.Icon(color="red", icon="info-sign"),
    ).add_to(m)

# Render
map_data = st_folium(m, width="100%", height=620, returned_objects=["last_clicked"])

# Handle click
if map_data and map_data.get("last_clicked"):
    lat = map_data["last_clicked"]["lat"]
    lon = map_data["last_clicked"]["lng"]

    if (lat, lon) != st.session_state.clicked_coords:
        st.session_state.clicked_coords = (lat, lon)
        st.session_state.clicked_village = find_village(gdf, lat, lon, name_field)
        st.rerun()

# Info panel
st.divider()
if st.session_state.clicked_village:
    st.success(f"📍 **Village:** {st.session_state.clicked_village}")
elif st.session_state.clicked_coords:
    lat, lon = st.session_state.clicked_coords
    st.warning(f"No village polygon found at ({lat:.5f}, {lon:.5f})")
else:
    st.info("Click on the map to identify a village.")
