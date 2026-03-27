import streamlit as st
import pandas as pd
import re
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
import io

# --- APP CONFIGURATION ---
st.set_page_config(page_title="Address Verifier Pro", layout="wide")

# Initialize Session Memory for the Map and Results
if 'map_data' not in st.session_state:
    st.session_state.map_data = None

# Geocoder setup
geolocator = Nominatim(user_agent="address_verifier_final_2026")

# --- NORMALIZATION LOGIC ---
def normalize_street(text):
    if not isinstance(text, str): return ""
    text = text.upper().strip()
    replacements = {
        r'\bST\b': 'STREET', r'\bAVE\b': 'AVENUE', r'\bRD\b': 'ROAD',
        r'\bDR\b': 'DRIVE', r'\bLN\b': 'LANE', r'\bBLVD\b': 'BOULEVARD',
        r'\bCT\b': 'COURT', r'\bPL\b': 'PLACE', r'\bTER\b': 'TERRACE',
        r'\bPKWY\b': 'PARKWAY'
    }
    for abbrev, full in replacements.items():
        text = re.sub(abbrev, full, text)
    return text

st.title("🚀 Professional Address Verifier")
st.markdown("Verify house number ranges against your master database and view locations on OpenStreetMap.")

# --- SIDEBAR - MASTER DATA ---
st.sidebar.header("1. Master Database")
master_file = st.sidebar.file_uploader("Upload Master CSV", type="csv")

if master_file:
    # Load and clean master data headers
    master_df = pd.read_csv(master_file)
    master_df.columns = [c.strip().lower() for c in master_df.columns]
    m_cols = master_df.columns.tolist()
    
    # Set default column mappings
    def_street = "street name" if "street name" in m_cols else m_cols[0]
    def_low = "low" if "low" in m_cols else m_cols[0]
    def_high = "high" if "high" in m_cols else m_cols[0]
    
    m_street = st.sidebar.selectbox("Street Name Column", m_cols, index=m_cols.index(def_street))
    m_low = st.sidebar.selectbox("Low Number Column", m_cols, index=m_cols.index(def_low))
    m_high = st.sidebar.selectbox("High Number Column", m_cols, index=m_cols.index(def_high))

    # Pre-normalize for speed
    master_df['norm_street'] = master_df[m_street].apply(normalize_street)

    # --- TABS ---
    mode = st.tabs(["Single Lookup", "Bulk Process"])

    # SINGLE LOOKUP TAB
    with mode[0]:
        search_query = st.text_input("Paste Full Address:", placeholder="e.g. 123 Main St", key="search_input")
        
        if st.button("Verify & Map"):
            # Use Regex to split number and street
            match_parse = re.match(r"(\d+)\s+(.*)", search_query.strip())
            
            if match_parse:
                num = int(match_parse.group(1))
                street_raw = match_parse.group(2).split(',')[0].strip()
                street_norm = normalize_street(street_raw)

                # Logic Check
                mask = (
                    master_df['norm_street'].str.contains(street_norm, na=False) &
                    (pd.to_numeric(master_df[m_low], errors='coerce') <= num) &
                    (pd.to_numeric(master_df[m_high], errors='coerce') >= num)
                )
                res = master_df[mask]

                if not res.empty:
                    # Capture coordinates
                    try:
                        loc = geolocator.geocode(search_query)
                        # Save to session state to prevent disappearing on rerun
                        st.session_state.map_data = {
                            "df": res.drop(columns=['norm_street']),
                            "query": search_query,
                            "coords": (loc.latitude, loc.longitude) if loc else None
                        }
                    except:
                        st.session_state.map_data = {
                            "df": res.drop(columns=['norm_street']),
                            "query": search_query,
                            "coords": None
                        }
                else:
                    st.session_state.map_data = None
                    st.error(f"❌ No range match found for {num} {street_norm}")
            else:
                st.warning("Please enter a format like: '100 Main St'")

        # Display persistent result if it exists in memory
        if st.session_state.map_data:
            data = st.session_state.map_data
            st.success(f"Verified Record for: {data['query']}")
            st.dataframe(data['df'])
            
            if data['coords']:
                m = folium.Map(location=data['coords'], zoom_start=16)
                folium.Marker(location=data['coords'], popup=data['query']).add_to(m)
                st_folium(m, width=900, height=500, key="persistent_osm_map")
            else:
                st.info("Address valid in CSV, but coordinates could not be found for the map.")

    # BULK PROCESS TAB
    with mode[1]:
        bulk_file = st.file_uploader("Upload CSV list to check", type="csv")
        if bulk_file:
            b_df = pd.read_csv(bulk_file)
            b_col = st.selectbox("Select address column to verify", b_df.columns)
            
            if st.button("Run Bulk Verification"):
                bulk_results = []
                for addr in b_df[b_col]:
                    p = re.match(r"(\d+)\s+(.*)", str(addr).strip())
                    status = "❌ No Match"
                    if p:
                        n, s_raw = int(p.group(1)), p.group(2).split(',')[0].strip()
                        s_norm = normalize_street(s_raw)
                        mask = (master_df['norm_street'].str.contains(s_norm, na=False) & 
                                (pd.to_numeric(master_df[m_low], errors='coerce') <= n) & 
                                (pd.to_numeric(master_df[m_high], errors='coerce') >= n))
                        if not master_df[mask].empty: status = "✅ Valid"
                    bulk_results.append({"Address": addr, "Result": status})
                
                final_bulk_df = pd.DataFrame(bulk_results)
                st.dataframe(final_bulk_df)
                st.download_button("📥 Download Results CSV", final_bulk_df.to_csv(index=False), "bulk_results.csv", "text/csv")

else:
    st.info("👋 Welcome! Please upload your Master CSV in the sidebar to start verifying addresses.")
