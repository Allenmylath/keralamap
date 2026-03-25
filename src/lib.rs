use wasm_bindgen::prelude::*;
use serde::{Deserialize, Serialize};
use geo::{Contains, Point, Polygon, LineString, MultiPolygon};

// ── Types ────────────────────────────────────────────────────────────────────

#[derive(Deserialize, Clone)]
struct FeatureCollection {
    features: Vec<Feature>,
}

#[derive(Deserialize, Clone)]
struct Feature {
    geometry: Option<Geometry>,
    properties: Option<serde_json::Value>,
}

#[derive(Deserialize, Clone)]
struct Geometry {
    #[serde(rename = "type")]
    geom_type: String,
    coordinates: serde_json::Value,
}

#[derive(Serialize)]
struct Stats {
    villages: usize,
    districts: usize,
}

// ── Exported functions ────────────────────────────────────────────────────────

/// Filter features by district name.
/// JS passes the full GeoJSON string + district name,
/// Rust returns a filtered GeoJSON string.
#[wasm_bindgen]
pub fn filter_by_district(geojson_str: &str, district: &str) -> String {
    let collection: FeatureCollection = match serde_json::from_str(geojson_str) {
        Ok(c) => c,
        Err(_) => return geojson_str.to_string(),
    };

    if district == "all" {
        return geojson_str.to_string();
    }

    let filtered: Vec<serde_json::Value> = collection
        .features
        .into_iter()
        .filter(|f| {
            f.properties
                .as_ref()
                .and_then(|p| p.get("DISTRICT"))
                .and_then(|v| v.as_str())
                .map(|d| d == district)
                .unwrap_or(false)
        })
        .map(|f| {
            // Re-serialize each feature back to JSON
            serde_json::to_value(&FeatureForOutput {
                r#type: "Feature".to_string(),
                geometry: f.geometry,
                properties: f.properties,
            })
            .unwrap_or(serde_json::Value::Null)
        })
        .collect();

    serde_json::json!({
        "type": "FeatureCollection",
        "features": filtered
    })
    .to_string()
}

/// Returns { villages: N, districts: M } as a JSON string.
#[wasm_bindgen]
pub fn get_stats(geojson_str: &str) -> String {
    let collection: FeatureCollection = match serde_json::from_str(geojson_str) {
        Ok(c) => c,
        Err(_) => return r#"{"villages":0,"districts":0}"#.to_string(),
    };

    let villages = collection.features.len();

    let mut district_set = std::collections::HashSet::new();
    for f in &collection.features {
        if let Some(props) = &f.properties {
            if let Some(d) = props.get("DISTRICT").and_then(|v| v.as_str()) {
                district_set.insert(d.to_string());
            }
        }
    }

    serde_json::to_string(&Stats {
        villages,
        districts: district_set.len(),
    })
    .unwrap_or_default()
}

/// Given lat/lng, returns the village NAME string, or empty string if no hit.
#[wasm_bindgen]
pub fn point_in_village(geojson_str: &str, lat: f64, lng: f64) -> String {
    let collection: FeatureCollection = match serde_json::from_str(geojson_str) {
        Ok(c) => c,
        Err(_) => return String::new(),
    };

    let point = Point::new(lng, lat); // geo uses (x=lng, y=lat)

    for feature in &collection.features {
        let geom = match &feature.geometry {
            Some(g) => g,
            None => continue,
        };

        let hit = match geom.geom_type.as_str() {
            "Polygon" => {
                parse_polygon(&geom.coordinates)
                    .map(|p| p.contains(&point))
                    .unwrap_or(false)
            }
            "MultiPolygon" => {
                parse_multipolygon(&geom.coordinates)
                    .map(|mp| mp.contains(&point))
                    .unwrap_or(false)
            }
            _ => false,
        };

        if hit {
            return feature
                .properties
                .as_ref()
                .and_then(|p| p.get("NAME"))
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
        }
    }

    String::new()
}

// ── Internal helpers ──────────────────────────────────────────────────────────

#[derive(Serialize)]
struct FeatureForOutput {
    r#type: String,
    geometry: Option<Geometry>,
    properties: Option<serde_json::Value>,
}

impl Serialize for Geometry {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeStruct;
        let mut st = s.serialize_struct("Geometry", 2)?;
        st.serialize_field("type", &self.geom_type)?;
        st.serialize_field("coordinates", &self.coordinates)?;
        st.end()
    }
}

fn parse_ring(coords: &serde_json::Value) -> Option<LineString<f64>> {
    let arr = coords.as_array()?;
    let points: Vec<(f64, f64)> = arr
        .iter()
        .filter_map(|c| {
            let pair = c.as_array()?;
            Some((pair.get(0)?.as_f64()?, pair.get(1)?.as_f64()?))
        })
        .collect();
    Some(LineString::from(points))
}

fn parse_polygon(coords: &serde_json::Value) -> Option<Polygon<f64>> {
    let rings = coords.as_array()?;
    let exterior = parse_ring(rings.get(0)?)?;
    let interiors: Vec<LineString<f64>> = rings[1..]
        .iter()
        .filter_map(parse_ring)
        .collect();
    Some(Polygon::new(exterior, interiors))
}

fn parse_multipolygon(coords: &serde_json::Value) -> Option<MultiPolygon<f64>> {
    let polys: Vec<Polygon<f64>> = coords
        .as_array()?
        .iter()
        .filter_map(parse_polygon)
        .collect();
    Some(MultiPolygon(polys))
}
