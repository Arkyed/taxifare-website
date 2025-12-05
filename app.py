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
from urllib.parse import urlencode, quote_plus
from geopy.distance import geodesic
from streamlit_extras.let_it_rain import rain
from streamlit_extras.stoggle import stoggle

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
    /* Ensure the page and body show the background stripes */
    html, body, .stApp {{
        min-height: 100vh;
        height: 100%;
        margin: 0;
        padding: 0;
        /* Horizontal stripes left-to-right (change angle to 90deg/0deg/45deg for vertical/diagonal) */
        background-image: repeating-linear-gradient(
            0deg,
            {USA_BLUE} 0 10px,
            {USA_WHITE} 10px 20px,
            {USA_RED} 20px 30px,
            {USA_WHITE} 30px 40px
        );
        background-attachment: fixed;
        background-size: auto;
        /* keep text readable */
        color: {CONTRAST_BLACK};
    }}

    /* Sidebar background */
    div[data-testid="stSidebar"] {{
            background-color: {MAIN_YELLOW} !important;
            color: {CONTRAST_BLACK} !important;
    }}

    /* Make the main content container have a centered horizontal gradient background */
    .block-container {{
        background: linear-gradient(
            90deg,
            rgba(255,255,255,0.0) 8%,
            rgba(255,255,255,0.95) 18%,
            rgba(255,255,255,0.95) 82%,
            rgba(255,255,255,0.0) 92%
        );
        border-radius: 12px;
        padding: 1.25rem;
        box-shadow: 0 6px 18px rgba(0,0,0,0.06);
    }}

    /* Buttons */
    .stButton>button {{
        background-color: {MAIN_YELLOW};
        color: {CONTRAST_BLACK};
        border: none;
    }}

    /* Small styling tweaks */
    h1, h2, h3 {{
        color: {MAIN_YELLOW};
    }}
    .folium-map {{
        display: block;
        margin: 0 auto;
        border-radius: 8px;
    }}

    /* Slider: rendre la piste et le "thumb" en jaune (MAIN_YELLOW) */
    /* Piste (track) */
    input[type="range"] {{
        -webkit-appearance: none;
        width: 100%;
        height: 10px;
        background: rgba(0,0,0,0.15); /* piste non-active */
        border-radius: 6px;
        outline: none;
    }}
    /* Remplissage avant le thumb (WebKit) : on simule en utilisant background en ligne */
    input[type="range"]::-webkit-slider-runnable-track {{
        background: linear-gradient(90deg, {MAIN_YELLOW} 0%, {MAIN_YELLOW} 100%);
        height: 10px;
        border-radius: 6px;
    }}
    input[type="range"]::-webkit-slider-thumb {{
        -webkit-appearance: none;
        margin-top: -3px; /* recentre le pouce verticalement */
        width: 18px;
        height: 18px;
        background: {MAIN_YELLOW};
        border: 2px solid {CONTRAST_BLACK};
        border-radius: 50%;
        box-shadow: 0 0 0 3px rgba(0,0,0,0.06);
        cursor: pointer;
    }}
    /* Firefox */
    input[type="range"]::-moz-range-track {{
        background: rgba(0,0,0,0.15);
        height: 10px;
        border-radius: 6px;
    }}
    input[type="range"]::-moz-range-progress {{
        background: {MAIN_YELLOW};
        height: 10px;
        border-radius: 6px;
    }}
    input[type="range"]::-moz-range-thumb {{
        width: 18px;
        height: 18px;
        background: {MAIN_YELLOW};
        border: 2px solid {CONTRAST_BLACK};
        border-radius: 50%;
        cursor: pointer;
    }}
    /* Edge / IE fallback */
    input[type="range"]::-ms-fill-lower {{
        background: {MAIN_YELLOW};
    }}
    input[type="range"]::-ms-thumb {{
        background: {MAIN_YELLOW};
        border: 2px solid {CONTRAST_BLACK};
    }}

    :root, .stApp {{
      --primaryColor: {MAIN_YELLOW};
    }}

    /* Map title style: centered and pushed down to avoid header overlap */
    .map-title {{
        text-align: center;
        margin-top: 48px; /* push down so it doesn't blend with Streamlit header */
        margin-bottom: 8px;
        font-weight: 600;
        color: {CONTRAST_BLACK};
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
    st.title("🚕 Fare Estimator")
    st.markdown("Enter pickup and dropoff addresses, or click the map to fill them.")

    # Pickup address input
    st.session_state["pickup_address"] = st.text_input(
        "Pickup address", value=st.session_state["pickup_address"], placeholder="e.g. 350 5th Ave, New York, NY"
    )

    # Distance display BETWEEN the two address inputs
    if st.session_state.get("pickup_coords") and st.session_state.get("dropoff_coords"):
        p_lat, p_lon = st.session_state["pickup_coords"]
        d_lat, d_lon = st.session_state["dropoff_coords"]
        try:
            dist_km = geodesic((p_lat, p_lon), (d_lat, d_lon)).km
            st.markdown(f"**Distance:** {dist_km:.2f} km ({dist_km/1.60934:.2f} miles)")
        except Exception:
            st.markdown("**Distance :** impossible à calculer")
    else:
        st.markdown("Distance : définie après avoir sélectionné Pickup & Dropoff sur la carte ou utilisez **Locate on map**")

    # Dropoff address input
    st.session_state["dropoff_address"] = st.text_input(
        "Dropoff address", value=st.session_state["dropoff_address"], placeholder="e.g. 1 Liberty Island, New York, NY"
    )

    # Collapsible instructions for the map (uses stoggle if available, else st.expander)
    _map_instructions = """
**Carte :**
- 1er clic = pickup
- 2e clic = dropoff
- Si les deux points sont déjà définis, un nouveau clic recommence la sélection (nouveau pickup).
Utilise le bouton *Clear coordinates* pour réinitialiser.
    """
    try:
        stoggle("Carte — Instructions", _map_instructions)
    except Exception:
        with st.expander("Carte — Instructions"):
            st.markdown(_map_instructions)

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
    if st.button("Estimate 🚕 fare"):
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
                # Build predict URL (ensure no duplicate slashes)
                predict_url = service_url.rstrip('/') + '/predict'

                # Use urlencode with quote_plus so spaces become '+' (matches your API example)
                query = urlencode(payload, quote_via=quote_plus)
                full_url = f"{predict_url}?{query}"

                try:
                    resp = requests.get(full_url, timeout=10)
                    """
                    # DEBUG: show status, headers, and body to help diagnose if needed
                    st.write("API status:", resp.status_code)
                    st.write("API headers:", dict(resp.headers))
                    st.write("API body:", resp.text[:2000])
                    """

                    resp.raise_for_status()
                    data = resp.json() if resp.content else None
                    # Robust parsing of common response formats (keeps your original logic)
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
                        rain('💲',72,7,[5,'infinite'])

                except requests.HTTPError as e:
                    # If you still see 405, show the raw response for debugging
                    if resp.status_code == 405:
                        st.error("API returned 405 Method Not Allowed. Tried GET to /predict; check API docs or service path.")
                    else:
                        st.error(f"API HTTP error: {e}")
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

# Tracer une ligne entre pickup et dropoff si les deux existent
if st.session_state.get("pickup_coords") and st.session_state.get("dropoff_coords"):
    p = st.session_state["pickup_coords"]
    d = st.session_state["dropoff_coords"]
    folium.PolyLine(locations=[p, d], color=CONTRAST_BLACK, weight=3, opacity=0.85).add_to(m)

# Show map and capture clicks. The return value contains "last_clicked"
st.markdown('<div class="map-title">Map (click to set coordinates)</div>', unsafe_allow_html=True)
cols = st.columns([1, 2, 1])
with cols[1]:
    map_data = st_folium(m, width=900, height=600)

# Si la carte a été cliquée, map_data contient 'last_clicked' avec lat/lng
if map_data and map_data.get("last_clicked"):
    clicked = map_data["last_clicked"]
    lat = clicked.get("lat")
    lon = clicked.get("lng")
    if lat is not None and lon is not None:
        # Reverse geocode le click en adresse
        address = reverse_geocode(lat, lon)

        # 1) Si pickup manquant -> on le définit
        if st.session_state["pickup_coords"] is None:
            st.session_state["pickup_coords"] = (lat, lon)
            if address:
                st.session_state["pickup_address"] = address
            st.success("Pickup sélectionné — cliquez de nouveau pour définir le dropoff")

        # 2) Sinon si dropoff manquant -> on le définit
        elif st.session_state["dropoff_coords"] is None:
            st.session_state["dropoff_coords"] = (lat, lon)
            if address:
                st.session_state["dropoff_address"] = address
            st.success("Dropoff sélectionné")

        # 3) Sinon (les deux sont déjà définis) -> on recommence : nouveau pickup, on efface dropoff
        else:
            st.session_state["pickup_coords"] = (lat, lon)
            st.session_state["dropoff_coords"] = None
            st.session_state["dropoff_address"] = ""
            if address:
                st.session_state["pickup_address"] = address
            st.info("Les deux points étaient définis — nouvelle sélection de Pickup commencée (cliquez pour définir le dropoff)")

# Bouton pour effacer les coords/addresses
with cols[1]:
    if st.button("Clear coordinates"):
        st.session_state["pickup_coords"] = None
        st.session_state["dropoff_coords"] = None
        st.session_state["pickup_address"] = ""
        st.session_state["dropoff_address"] = ""
        st.success("Pickup et Dropoff effacés")
