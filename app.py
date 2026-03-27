import streamlit as st
import pandas as pd
import re
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
import io

# 1. PASSWORD PROTECTION
def check_password():
    if "password_correct" not in st.session_state:
        st.text_input("Enter App Password", type="password", on_change=lambda: st.session_state.update({"password_correct": st.session_state.password == "mysecret123"}), key="password")
        return False
    return st.session_state["password_correct"]

if not check_password():
    st.stop()

# 2. ADDRESS NORMALIZATION LOGIC
def normalize_street(text):
    """Converts abbreviations to full words for better matching."""
    if not isinstance(text, str): return ""
    text = text.upper().strip()
    # Common mapping
    replacements = {
        r'\bST\b': 'STREET',
        r'\bAVE\b': 'AVENUE',
        r'\bRD\b': 'ROAD',
        r'\bDR\b': 'DRIVE',
        r'\bLN\b': 'LANE',
        r'\bBLVD\b': 'BOULEVARD',
        r'\bCT\b': 'COURT',
        r'\bPL\b': 'PLACE',
        r'\bTER\b': 'TERRACE',
        r'\bPKWY\b': 'PARKWAY'
    }
    for abbrev, full in replacements.items():
        text = re.sub(abbrev, full, text)
    return text

# --- APP START ---
st.set_page_config(page_title="Pro Address Verifier", layout="wide")
geolocator = Nominatim(user_agent="final_verifier_2026")

st.title("🚀 Address Verifier (Auto-Format Suffixes)")

# 3. LOAD MASTER DATA
st.sidebar.header("1. Master Database")
master_file = st.sidebar.file_uploader("Upload Master CSV", type="csv")

if master_file:
    master_df = pd.read_csv(master_file)
    master_df.columns = [c.strip().lower() for c in master_df.columns]
    m_cols = master_df.columns.tolist()
    
    # Defaults
    def_street = "street name" if "street name" in m_cols else m_cols[0]
    def_low = "low" if "low" in m_cols else m_cols[0]
    def_high = "high" if "high" in m_cols else m_cols[0]
    
    m_street = st.sidebar.selectbox("Street Name Column", m_cols, index=m_cols.index(def_street))
    m_low = st.sidebar.selectbox("Low Number Column", m_cols, index=m_cols.index(def_low))
    m_high = st.sidebar.selectbox("High Number Column", m_cols, index=m_cols.index(def_high))

    # Pre-normalize the master list for faster bulk searching
    master_df['norm_street'] = master_df[m_street].apply(normalize_street)

    # 4. SEARCH MODES
    mode = st.tabs(["Single Lookup", "Bulk Process"])

    with mode[0]:
        search_query = st.text_input("Paste Full Address:", placeholder="e.g. 500 Park Ave")
        if st.button("Verify Single") and search_query:
            match_parse = re.match(r"(\d+)\s+(.*)", search_query.strip())
            if match_parse:
                num = int(match_parse.group(1))
                street_raw = match_parse.group(2).split(',')[0].strip()
                street_norm = normalize_street(street_raw)

                # Logic: Compare normalized versions
                mask = (
                    master_df['norm_street'].str.contains(street_norm, na=False) &
                    (pd.to_numeric(master_df[m_low], errors='coerce') <= num) &
                    (pd.to_numeric(master_df[m_high], errors='coerce') >= num)
                )
                res = master_df[mask]

                if not res.empty:
                    st.success(f"✅ Match Found: {num} {street_norm}")
                    st.dataframe(res.drop(columns=['norm_street'])) # Hide the helper column
                    # Mapping
                    try:
                        loc = geolocator.geocode(search_query)
                        if loc:
                            m = folium.Map(location=[loc.latitude, loc.longitude], zoom_start=16)
                            folium.Marker([loc.latitude, loc.longitude]).add_to(m)
                            st_folium(m, width=700, height=400)
                    except: st.warning("Map service busy.")
                else:
                    st.error(f"❌ No range found for {num} {street_norm}")

    with mode[1]:
        bulk_file = st.file_uploader("Upload CSV to check", type="csv")
        if bulk_file:
            b_df = pd.read_csv(bulk_file)
            b_col = st.selectbox("Select address column", b_df.columns)
            
            if st.button("Start Bulk Verify"):
                results = []
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
                    results.append({"Address": addr, "Result": status})
                
                out_df = pd.DataFrame(results)
                st.dataframe(out_df)
                st.download_button("📥 Download Results", out_df.to_csv(index=False), "bulk_results.csv", "text/csv")
else:
    st.info("Please upload your Master CSV to begin.")
    
with st.expander("❓ How to use this app / CSV Requirements"):
    st.markdown("""
    ### 📖 User Guide
    
    **1. Master CSV Requirements**
    Your master file should have columns for **Street Name**, **Low** (min number), and **High** (max number).
    
    **2. Address Formatting**
    - Always start with the house number (e.g., `123 Main St`).
    - The app handles abbreviations like `St`, `Ave`, `Rd`, and `Blvd` automatically.
    
    **3. Bulk Uploads**
    - Upload a CSV containing a list of full addresses.
    - Select the column name that contains the addresses.
    - Click 'Start Bulk Verify' to get a downloadable report.
    """)