# app.py
# Streamlit Taxi Fare Estimator for NYC
# Comments throughout explain how to adjust behavior and styling.

import streamlit as st
from datetime import datetime, date, time
import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderServiceError
import folium
from streamlit_folium import st_folium

# Page config for layout and title
st.set_page_config(page_title="NYC Taxi Fare Estimator", layout="wide")

# ------------------------
# Styling / Theme
# ------------------------
# Colors:
# - main: #FFDE38 (yellow)
# - contrast: black
# - usa_red: #cd0039
# - usa_white: #ffffff
# - usa_blue: #003b79
#
# You can edit these variables to change the look.
MAIN_YELLOW = "#FFDE38"
CONTRAST_BLACK = "#000000"
USA_RED = "#cd0039"
USA_WHITE = "#ffffff"
USA_BLUE = "#003b79"

# Minimal CSS to adapt page and sidebar colors. Streamlit class names change,
# so this is intentionally lightweight. Edit or expand if you want more control.
st.markdown(
    f"""
    <style>
    /* Page background and text */
    .stApp {{
        background-color: {USA_WHITE};
        color: {CONTRAST_BLACK};
    }}
    /* Sidebar background */
    .css-1d391kg .css-1d391kg{{}}
    .block-container .sidebar .stButton, .css-1v0mbdj .stButton {{
        border-radius: 8px;
    }}
    /* Streamlit button primary color */
    .stButton>button {{
        background-color: {MAIN_YELLOW};
        color: {CONTRAST_BLACK};
        border: none;
    }}
    /* Header style */
    h1, h2, h3 {{
        color: {CONTRAST_BLACK};
    }}
    /* Small adjustments for folium map container */
    .folium-map {{
        border-radius: 8px;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------
# Utility: Geolocator (Nominatim)
# ------------------------
# We use Nominatim (OpenStreetMap). If you prefer a different geocoding service,
# replace these functions accordingly. Nominatim's usage policy requires a
# descriptive `user_agent` — change "taxi_fare_app" if you deploy publicly.
@st.cache_resource
def get_geolocator():
    return Nominatim(user_agent="taxi_fare_app")

geolocator = get_geolocator()

# Geocode an address (returns (lat, lon) or None)
@st.cache_data(show_spinner=False)
def geocode_address(address: str):
    if not address or address.strip() == "":
        return None
    try:
        loc = geolocator.geocode(address, timeout=10)
        if loc:
            return (loc.latitude, loc.longitude)
    except GeocoderServiceError:
        return None
    return None

# Reverse geocode (lat, lon) -> human-readable address (or None)
@st.cache_data(show_spinner=False)
def reverse_geocode(lat: float, lon: float):
    try:
        loc = geolocator.reverse((lat, lon), timeout=10, exactly_one=True)
        if loc:
            return loc.address
    except GeocoderServiceError:
        return None
    return None

# ------------------------
# Session state: ensure keys exist to hold addresses and coords
# ------------------------
if "pickup_address" not in st.session_state:
    st.session_state["pickup_address"] = ""
if "dropoff_address" not in st.session_state:
    st.session_state["dropoff_address"] = ""
if "pickup_coords" not in st.session_state:
    st.session_state["pickup_coords"] = None  # tuple (lat, lon)
if "dropoff_coords" not in st.session_state:
    st.session_state["dropoff_coords"] = None

# ------------------------
# Sidebar: inputs for addresses, passengers, date/time
# ------------------------
with st.sidebar:
    st.title("Taxi Fare Estimator")
    st.markdown("Enter pickup and dropoff addresses, or click the map to fill them.")

    # Address inputs (editable)
    st.session_state["pickup_address"] = st.text_input(
        "Pickup address", value=st.session_state["pickup_address"], placeholder="e.g. 350 5th Ave, New York, NY"
    )
    st.session_state["dropoff_address"] = st.text_input(
        "Dropoff address", value=st.session_state["dropoff_address"], placeholder="e.g. 1 Liberty Island, New York, NY"
    )

    # Controls to pick whether map clicks set pickup or dropoff coordinate
    map_click_target = st.radio("Map click fills", ("Pickup", "Dropoff"))

    # Button to geocode both addresses and show them on the map
    if st.button("Locate on map"):
        # Geocode pickup
        pickup_coords = geocode_address(st.session_state["pickup_address"])
        if pickup_coords:
            st.session_state["pickup_coords"] = pickup_coords
        else:
            st.warning("Couldn't geocode pickup address. Try a more specific address.")

        # Geocode dropoff
        dropoff_coords = geocode_address(st.session_state["dropoff_address"])
        if dropoff_coords:
            st.session_state["dropoff_coords"] = dropoff_coords
        else:
            st.warning("Couldn't geocode dropoff address. Try a more specific address.")

    # Passenger slider 1..8
    passengers = st.slider("Passengers", min_value=1, max_value=8, value=1, step=1)

    # Date and time input for pickup
    pickup_date = st.date_input("Pickup date", value=date.today())
    pickup_time = st.time_input("Pickup time", value=datetime.now().time().replace(microsecond=0))

    # Button to call API and get price
    if st.button("Get estimated fare"):
        # Validate coordinates: if missing, try to geocode from typed addresses
        if st.session_state["pickup_coords"] is None:
            st.session_state["pickup_coords"] = geocode_address(st.session_state["pickup_address"])
        if st.session_state["dropoff_coords"] is None:
            st.session_state["dropoff_coords"] = geocode_address(st.session_state["dropoff_address"])

        if st.session_state["pickup_coords"] is None or st.session_state["dropoff_coords"] is None:
            st.error("Both pickup and dropoff coordinates are required. Please provide addresses or click the map.")
        else:
            # Build payload for API. Adjust keys if your API expects different names.
            pickup_lat, pickup_lon = st.session_state["pickup_coords"]
            dropoff_lat, dropoff_lon = st.session_state["dropoff_coords"]

            # Format datetime string for API. Change format if your API expects different timezone/format.
            pickup_datetime = datetime.combine(pickup_date, pickup_time).strftime("%Y-%m-%d %H:%M:%S")

            # Build payload as before (ensure types)
            payload = {
                "pickup_datetime": pickup_datetime,                     # "YYYY-MM-DD HH:MM:SS"
                "pickup_longitude": float(pickup_lon),
                "pickup_latitude": float(pickup_lat),
                "dropoff_longitude": float(dropoff_lon),
                "dropoff_latitude": float(dropoff_lat),
                "passenger_count": int(passengers),
            }

            # Read SERVICE_URL from secrets.toml (streamlit/secrets.toml)
            try:
                service_url = st.secrets["API_related"]["SERVICE_URL"]
            except Exception:
                st.error("API URL not found in secrets. Please add it to streamlit/secrets.toml as [API_related] SERVICE_URL = '...'")
                service_url = None

            if service_url:
                try:
                    # requests.post(json=...) sets Content-Type automatically
                    resp = requests.post(service_url, json=payload, timeout=10)
                    resp.raise_for_status()
                    data = resp.json() if resp.content else None

                    # Robust parsing of common response formats
                    prediction = None
                    if data is None:
                        # maybe API returned a plain number in text
                        try:
                            prediction = float(resp.text.strip())
                        except Exception:
                            prediction = None
                    elif isinstance(data, (int, float)):
                        prediction = float(data)
                    elif isinstance(data, dict):
                        prediction = data.get("prediction") or data.get("fare") or data.get("pred")
                        if prediction is None and "predictions" in data:
                            try:
                                prediction = float(data["predictions"][0])
                            except Exception:
                                prediction = None

                    if prediction is None:
                        st.error(f"Couldn't parse prediction from API response: {data or resp.text}")
                    else:
                        st.success(f"Estimated fare: 💲{float(prediction):.2f}")
                        st.balloons()

                except requests.RequestException as e:
                    st.error(f"API request failed: {e}")

# ------------------------
# Main area: interactive map + info
# ------------------------
# Center the map in NYC by default
NYC_CENTER = (40.7128, -74.0060)
map_center = NYC_CENTER

# If both coords are present, center on midpoint
if st.session_state["pickup_coords"] and st.session_state["dropoff_coords"]:
    p_lat, p_lon = st.session_state["pickup_coords"]
    d_lat, d_lon = st.session_state["dropoff_coords"]
    map_center = ((p_lat + d_lat) / 2, (p_lon + d_lon) / 2)
elif st.session_state["pickup_coords"]:
    map_center = st.session_state["pickup_coords"]
elif st.session_state["dropoff_coords"]:
    map_center = st.session_state["dropoff_coords"]

# Build folium map
m = folium.Map(location=map_center, zoom_start=12, tiles="CartoDB positron")

# Add pickup marker (yellow)
if st.session_state["pickup_coords"]:
    lat, lon = st.session_state["pickup_coords"]
    folium.CircleMarker(
        location=(lat, lon),
        radius=8,
        color=MAIN_YELLOW,
        fill=True,
        fill_color=MAIN_YELLOW,
        fill_opacity=0.9,
        popup=f"Pickup: {st.session_state['pickup_address'] or 'Selected on map'}",
    ).add_to(m)

# Add dropoff marker (blue)
if st.session_state["dropoff_coords"]:
    lat, lon = st.session_state["dropoff_coords"]
    folium.CircleMarker(
        location=(lat, lon),
        radius=8,
        color=USA_BLUE,
        fill=True,
        fill_color=USA_BLUE,
        fill_opacity=0.9,
        popup=f"Dropoff: {st.session_state['dropoff_address'] or 'Selected on map'}",
    ).add_to(m)

# Show map and capture clicks. The return value contains "last_clicked"
st.markdown("### Map (click to set coordinates)")
map_data = st_folium(m, width=900, height=600)

# If the map was clicked, map_data contains 'last_clicked' with lat/lng
if map_data and map_data.get("last_clicked"):
    clicked = map_data["last_clicked"]
    lat = clicked.get("lat")
    lon = clicked.get("lng")
    if lat is not None and lon is not None:
        # Reverse geocode the click to an address string
        address = reverse_geocode(lat, lon)
        if map_click_target == "Pickup":
            st.session_state["pickup_coords"] = (lat, lon)
            if address:
                st.session_state["pickup_address"] = address
            st.success("Map click saved to Pickup")
        else:
            st.session_state["dropoff_coords"] = (lat, lon)
            if address:
                st.session_state["dropoff_address"] = address
            st.success("Map click saved to Dropoff")

# Small note explaining interactivity
st.markdown(
    """
    - Use the sidebar to enter addresses and press **Locate on map** to geocode them.
    - Or select whether **Map click fills** Pickup/Dropoff and click on the map to set coordinates.
    - Press **Get estimated fare** once both pickup and dropoff are set.
    """
)