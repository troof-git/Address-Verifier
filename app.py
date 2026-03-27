import streamlit as st
import pandas as pd
import re
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
import io

# --- APP CONFIGURATION ---
st.set_page_config(page_title="Address Verifier", layout="wide")

if 'map_data' not in st.session_state:
    st.session_state.map_data = None

geolocator = Nominatim(user_agent="final_geo_verifier_2026")

def normalize_street(text):
    if not isinstance(text, str): return ""
    # 1. Basic Cleaning
    text = text.upper().strip()
    
    # 2. Directional Mapping (Handles N, S, E, W)
    directions = {
        r'\bN\b': 'NORTH', r'\bS\b': 'SOUTH', 
        r'\bE\b': 'EAST', r'\bW\b': 'WEST',
        r'\bNE\b': 'NORTHEAST', r'\bNW\b': 'NORTHWEST',
        r'\bSE\b': 'SOUTHEAST', r'\bSW\b': 'SOUTHWEST'
    }
    
    # 3. Suffix Mapping
    suffixes = {
        r'\bST\b': 'STREET', r'\bAVE\b': 'AVENUE', r'\bRD\b': 'ROAD',
        r'\bDR\b': 'DRIVE', r'\bLN\b': 'LANE', r'\bBLVD\b': 'BOULEVARD',
        r'\bCT\b': 'COURT', r'\bPL\b': 'PLACE', r'\bTER\b': 'TERRACE',
        r'\bPKWY\b': 'PARKWAY'
    }
    
    # Apply Directional Replacements
    for abbrev, full in directions.items():
        text = re.sub(abbrev, full, text)
    # Apply Suffix Replacements
    for abbrev, full in suffixes.items():
        text = re.sub(abbrev, full, text)
        
    # 4. Unit Filtering (Remove common Apartment/Suite markers and anything after)
    # This stops "Apt 4" or "Suite B" from breaking the street match
    text = re.split(r'\b(APT|STE|UNIT|SUITE|#|FL)\b', text)[0].strip()
    
    return text

st.title("🌍 Address Verifier")
st.markdown("Handles **Directions** (N, S, E, W), **Split Homes** (123A), and **Unit Numbers** (Apt 4).")

# --- SIDEBAR - MASTER DATA ---
st.sidebar.header("1. Master Database")
master_file = st.sidebar.file_uploader("Upload Master CSV", type="csv")

if master_file:
    master_df = pd.read_csv(master_file)
    master_df.columns = [c.strip().lower() for c in master_df.columns]
    m_cols = master_df.columns.tolist()
    
    m_street = st.sidebar.selectbox("Street Name Column", m_cols, index=0)
    m_low = st.sidebar.selectbox("Low Number Column", m_cols, index=1)
    m_high = st.sidebar.selectbox("High Number Column", m_cols, index=2)

    # Clean Master List
    master_df['norm_street'] = master_df[m_street].apply(normalize_street)
    master_df[m_low] = pd.to_numeric(master_df[m_low], errors='coerce')
    master_df[m_high] = pd.to_numeric(master_df[m_high], errors='coerce')

    # --- TABS ---
    mode = st.tabs(["Single Lookup", "Bulk Process"])

    with mode[0]:
        search_query = st.text_input("Paste Full Address:", placeholder="e.g. 123N Main St Apt 4")
        
        if st.button("Verify & Map"):
            # Regex captures the house number part (even with letters) and the rest
            match_parse = re.match(r"([0-9a-zA-Z-]+)\s+(.*)", search_query.strip())
            
            if match_parse:
                raw_num = match_parse.group(1)
                clean_num_str = re.sub(r"\D", "", raw_num) # Strip letters from house number
                
                if clean_num_str:
                    num = int(clean_num_str)
                    street_raw = match_parse.group(2)
                    street_norm = normalize_street(street_raw)

                    # Range Check
                    mask = (
                        master_df['norm_street'].str.contains(street_norm, na=False) &
                        (master_df[m_low] <= num) &
                        (master_df[m_high] >= num)
                    )
                    res = master_df[mask]

                    if not res.empty:
                        try:
                            loc = geolocator.geocode(search_query)
                            st.session_state.map_data = {
                                "df": res.drop(columns=['norm_street']),
                                "query": search_query,
                                "cleaned_num": num,
                                "cleaned_street": street_norm,
                                "coords": (loc.latitude, loc.longitude) if loc else None
                            }
                        except:
                            st.session_state.map_data = {
                                "df": res.drop(columns=['norm_street']),
                                "query": search_query,
                                "cleaned_num": num,
                                "cleaned_street": street_norm,
                                "coords": None
                            }
                    else:
                        st.session_state.map_data = None
                        st.error(f"❌ No match for house #{num} on {street_norm}")
                else:
                    st.error("Invalid house number.")
            else:
                st.warning("Use format: '123 N Main St'")

        if st.session_state.map_data:
            d = st.session_state.map_data
            st.success(f"✅ Verified: {d['query']}")
            st.caption(f"Search Logic: House #{d['cleaned_num']} on '{d['cleaned_street']}'")
            st.table(d['df'])
            
            if d['coords']:
                m = folium.Map(location=d['coords'], zoom_start=16)
                folium.Marker(location=d['coords'], popup=d['query']).add_to(m)
                st_folium(m, width=900, height=500, key="persistent_ultra_map")

    with mode[1]:
        bulk_file = st.file_uploader("Upload CSV to check", type="csv")
        if bulk_file:
            b_df = pd.read_csv(bulk_file)
            b_col = st.selectbox("Select address column", b_df.columns)
            
            if st.button("Run Bulk Verify"):
                bulk_results = []
                for addr in b_df[b_col]:
                    p = re.match(r"([0-9a-zA-Z-]+)\s+(.*)", str(addr).strip())
                    status = "❌ No Match"
                    if p:
                        clean_n = re.sub(r"\D", "", p.group(1))
                        if clean_n:
                            n = int(clean_n)
                            s_norm = normalize_street(p.group(2))
                            mask = (master_df['norm_street'].str.contains(s_norm, na=False) & 
                                    (master_df[m_low] <= n) & 
                                    (master_df[m_high] >= n))
                            if not master_df[mask].empty: status = f"✅ Valid"
                    bulk_results.append({"Address": addr, "Result": status})
                
                final_bulk_df = pd.DataFrame(bulk_results)
                st.dataframe(final_bulk_df)
                st.download_button("📥 Download Results", final_bulk_df.to_csv(index=False), "bulk_results.csv", "text/csv")
else:
    st.info("Upload your Master CSV to begin.")
