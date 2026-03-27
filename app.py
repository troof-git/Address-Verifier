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

geolocator = Nominatim(user_agent="multi_segment_verifier_2026")

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

st.title("🌍 Address Verifier")
st.markdown("This version identifies all matching street segments for overlapping or split ranges.")

# --- SIDEBAR - MASTER DATA ---
st.sidebar.header("1. Master Database")
master_file = st.sidebar.file_uploader("Upload Master CSV", type="csv")

if master_file:
    master_df = pd.read_csv(master_file)
    master_df.columns = [c.strip().lower() for c in master_df.columns]
    m_cols = master_df.columns.tolist()
    
    def_street = "street name" if "street name" in m_cols else m_cols[0]
    def_low = "low" if "low" in m_cols else m_cols[0]
    def_high = "high" if "high" in m_cols else m_cols[0]
    
    m_street = st.sidebar.selectbox("Street Name Column", m_cols, index=m_cols.index(def_street))
    m_low = st.sidebar.selectbox("Low Number Column", m_cols, index=m_cols.index(def_low))
    m_high = st.sidebar.selectbox("High Number Column", m_cols, index=m_cols.index(def_high))

    # Clean and pre-normalize Master List
    master_df['norm_street'] = master_df[m_street].apply(normalize_street)
    # Ensure low/high are treated as numbers
    master_df[m_low] = pd.to_numeric(master_df[m_low], errors='coerce')
    master_df[m_high] = pd.to_numeric(master_df[m_high], errors='coerce')

    # --- TABS ---
    mode = st.tabs(["Single Lookup", "Bulk Process"])

    with mode[0]:
        search_query = st.text_input("Paste Full Address:", placeholder="e.g. 450 Main St", key="search_input")
        
        if st.button("Verify & Map"):
            match_parse = re.match(r"(\d+)\s+(.*)", search_query.strip())
            
            if match_parse:
                num = int(match_parse.group(1))
                street_raw = match_parse.group(2).split(',')[0].strip()
                street_norm = normalize_street(street_raw)

                # Find ALL rows where the street matches AND the number is in range
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
                            "coords": (loc.latitude, loc.longitude) if loc else None,
                            "count": len(res)
                        }
                    except:
                        st.session_state.map_data = {
                            "df": res.drop(columns=['norm_street']),
                            "query": search_query,
                            "coords": None,
                            "count": len(res)
                        }
                else:
                    st.session_state.map_data = None
                    st.error(f"❌ No matching segment found for {num} {street_norm}.")
            else:
                st.warning("Please enter a format like: '100 Main St'")

        if st.session_state.map_data:
            data = st.session_state.map_data
            st.success(f"✅ Found {data['count']} matching segment(s) for: {data['query']}")
            st.table(data['df']) # Using st.table to show all matching segments clearly
            
            if data['coords']:
                m = folium.Map(location=data['coords'], zoom_start=16)
                folium.Marker(location=data['coords'], popup=data['query']).add_to(m)
                st_folium(m, width=900, height=500, key="persistent_osm_map")

    with mode[1]:
        # Bulk Process remains robust to multi-segments
        bulk_file = st.file_uploader("Upload CSV list to check", type="csv")
        if bulk_file:
            b_df = pd.read_csv(bulk_file)
            b_col = st.selectbox("Select address column", b_df.columns)
            
            if st.button("Run Bulk Verification"):
                bulk_results = []
                for addr in b_df[b_col]:
                    p = re.match(r"(\d+)\s+(.*)", str(addr).strip())
                    status = "❌ No Match"
                    if p:
                        n, s_raw = int(p.group(1)), p.group(2).split(',')[0].strip()
                        s_norm = normalize_street(s_raw)
                        # Check if ANY row in master matches
                        mask = (master_df['norm_street'].str.contains(s_norm, na=False) & 
                                (master_df[m_low] <= n) & 
                                (master_df[m_high] >= n))
                        if not master_df[mask].empty: 
                            status = f"✅ Valid ({len(master_df[mask])} seg)"
                    bulk_results.append({"Address": addr, "Result": status})
                
                final_bulk_df = pd.DataFrame(bulk_results)
                st.dataframe(final_bulk_df)
                st.download_button("📥 Download Results", final_bulk_df.to_csv(index=False), "bulk_results.csv", "text/csv")
else:
    st.info("Please upload your Master CSV to start.")
