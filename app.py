import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Point

# ── Config ────────────────────────────────────────────────────────────────────

GEOJSON_PATH        = "village.geojson"
VILLAGE_NAME_FIELD  = "NAME"
SIMPLIFY_TOLERANCE  = 0.001   # ~100m — invisible at zoom 8–10, cuts vertices ~70%

MAP_CENTER          = [10.8505, 76.2711]
MAP_ZOOM            = 8
HIGHLIGHT_COLOR     = "#FF5733"
DEFAULT_FILL_COLOR  = "#3186cc"

# ── Load + clean + simplify (runs once, fully cached) ─────────────────────────

@st.cache_data
def load_geodata(path: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)

    # Fix CRS if needed
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    # Drop Pondicherry — 1 village, not Kerala
    gdf = gdf[gdf["STATE"] == "Kerala"].reset_index(drop=True)

    # Drop null geometries
    gdf = gdf[gdf.geometry.notna()].reset_index(drop=True)

    # Simplify — biggest performance win
    gdf["geometry"] = gdf.geometry.simplify(
        tolerance=SIMPLIFY_TOLERANCE,
        preserve_topology=True
    )

    return gdf


# ── Cache the serialized GeoJSON string separately ────────────────────────────
# Avoids re-running gdf.to_json() (slow for 11MB) on every Streamlit rerun

@st.cache_data
def get_geojson_str(gdf: gpd.GeoDataFrame) -> str:
    return gdf.to_json()


# ── Fast point-in-polygon via spatial index ───────────────────────────────────

def find_village(gdf: gpd.GeoDataFrame, lat: float, lon: float) -> str | None:
    pt = Point(lon, lat)
    candidates = list(gdf.sindex.intersection(pt.bounds))
    for i in candidates:
        if gdf.iloc[i].geometry.contains(pt):
            return gdf.iloc[i][VILLAGE_NAME_FIELD]
    return None


# ── Build Folium map ──────────────────────────────────────────────────────────

def build_map(geojson_str: str, clicked_village: str | None) -> folium.Map:
    import json

    m = folium.Map(location=MAP_CENTER, zoom_start=MAP_ZOOM, tiles="CartoDB positron")

    def style_fn(feature):
        is_selected = (
            clicked_village is not None
            and feature["properties"].get(VILLAGE_NAME_FIELD) == clicked_village
        )
        return {
            "fillColor":   HIGHLIGHT_COLOR if is_selected else DEFAULT_FILL_COLOR,
            "color":       "white",
            "weight":      0.5,
            "fillOpacity": 0.65 if is_selected else 0.3,
        }

    folium.GeoJson(
        data=json.loads(geojson_str),
        name="Villages",
        style_function=style_fn,
        highlight_function=lambda _: {
            "fillColor":   "#ffff00",
            "color":       "white",
            "weight":      1.5,
            "fillOpacity": 0.7,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=[VILLAGE_NAME_FIELD],
            aliases=["Village:"],
            sticky=False,
        ),
    ).add_to(m)

    # Needed to capture clicks through the GeoJson layer
    # CSS hides the coordinate popup it would normally show
    folium.LatLngPopup().add_to(m)
    m.get_root().html.add_child(folium.Element("""
    <style>
        .leaflet-popup-content-wrapper,
        .leaflet-popup-tip-container { display: none !important; }
    </style>
    """))

    return m


# ── App ───────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Kerala Village Map", layout="wide")
st.title("🗺️ Kerala Village Map")
st.caption("Hover to see village name. Click to identify and highlight.")

# Load data (cached — runs only once)
try:
    gdf = load_geodata(GEOJSON_PATH)
except Exception as e:
    st.error(f"Could not load `{GEOJSON_PATH}`: {e}")
    st.stop()

# Serialize (cached — runs only once)
geojson_str = get_geojson_str(gdf)

# Session state
if "clicked_village" not in st.session_state:
    st.session_state.clicked_village = None
if "clicked_coords" not in st.session_state:
    st.session_state.clicked_coords = None

# Build map
m = build_map(geojson_str, st.session_state.clicked_village)

# Add result marker on top (not cached, always fresh)
if st.session_state.clicked_coords:
    lat, lon = st.session_state.clicked_coords
    label = st.session_state.clicked_village or "No village found"
    folium.Marker(
        location=[lat, lon],
        popup=folium.Popup(f"<b>{label}</b>", max_width=220),
        tooltip=label,
        icon=folium.Icon(color="red", icon="info-sign"),
    ).add_to(m)

# Render map
map_data = st_folium(m, width="100%", height=640, returned_objects=["last_clicked"])

# Handle click
if map_data and map_data.get("last_clicked"):
    lat = map_data["last_clicked"]["lat"]
    lon = map_data["last_clicked"]["lng"]

    if (lat, lon) != st.session_state.clicked_coords:
        st.session_state.clicked_coords = (lat, lon)
        st.session_state.clicked_village = find_village(gdf, lat, lon)
        st.rerun()

# Info panel
st.divider()
if st.session_state.clicked_village:
    st.success(f"📍 **Village:** {st.session_state.clicked_village}")
elif st.session_state.clicked_coords:
    lat, lon = st.session_state.clicked_coords
    st.warning(f"No village found at ({lat:.5f}, {lon:.5f}) — try clicking inside a boundary.")
else:
    st.info("Click on the map to identify a village.")
