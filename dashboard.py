import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import os
import xml.etree.ElementTree as ET
from datetime import datetime
import json

st.set_page_config(
    page_title="JoyAndCo Product Feed Generator",
    page_icon="🛒",
    layout="wide"
)

# Replace with your GitHub username and repo name
GITHUB_USER = "boopin"
GITHUB_REPO = "joyandco-product-crawler"
GITHUB_BRANCH = "main"

# Function to get file content from GitHub
def get_github_file(path):
    url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{path}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    return None

# Function to get GitHub Actions status
def get_github_actions_status():
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/actions/runs"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            runs = response.json().get("workflow_runs", [])
            if runs:
                latest_run = runs[0]
                return {
                    "status": latest_run.get("conclusion") or "running",
                    "time": latest_run.get("updated_at"),
                    "url": latest_run.get("html_url")
                }
    except Exception as e:
        st.error(f"Error fetching GitHub status: {e}")
    return None

# Function to get CSV feed data
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_csv_feed_data():
    csv_content = get_github_file("feeds/google_shopping_feed.csv")
    if csv_content:
        try:
            # Use StringIO to convert string to file-like object
            from io import StringIO
            return pd.read_csv(StringIO(csv_content))
        except Exception as e:
            st.error(f"Error parsing CSV: {e}")
    return pd.DataFrame()

# Main content
st.title("JoyAndCo Product Feed Generator")
st.markdown("Monitor and control product feeds for Google and Meta shopping ads")

# Sidebar
st.sidebar.header("Controls")

# Manual trigger instructions
st.sidebar.markdown("""
## Manual Feed Generation
The crawler runs daily via GitHub Actions.

To manually trigger a new feed generation:
1. [Go to Actions on GitHub](https://github.com/{GITHUB_USER}/{GITHUB_REPO}/actions)
2. Click on "Generate JoyAndCo Product Feeds"
3. Click "Run workflow"
""")

# Main tabs
tab1, tab2 = st.tabs(["📊 Dashboard", "🔍 Feed Preview"])

with tab1:
    # GitHub Actions status
    github_status = get_github_actions_status()
    if github_status:
        status_color = "green" if github_status["status"] == "success" else "orange" if github_status["status"] == "running" else "red"
        st.markdown(f"""
        ### GitHub Actions Status
        <span style="color:{status_color};font-weight:bold;">{github_status["status"].upper()}</span>
        
        Last run: {github_status["time"]}
        
        [View Details]({github_status["url"]})
        """, unsafe_allow_html=True)
    else:
        st.warning("Could not fetch GitHub Actions status")
    
    # Feed data
    df = get_csv_feed_data()
    
    # Display metrics
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Total Products", len(df) if not df.empty else 0)
    
    with col2:
        st.metric("Feed Status", "Active" if not df.empty else "Not Generated")
    
    # Price distribution
    if not df.empty and 'price' in df.columns:
        try:
            st.subheader("Price Distribution")
            # Convert price to numeric, coercing errors to NaN
            df['price'] = pd.to_numeric(df['price'], errors='coerce')
            # Drop NaN values
            df_clean = df.dropna(subset=['price'])
            if not df_clean.empty:
                fig = px.histogram(df_clean, x="price", nbins=20, title="Product Price Distribution")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No valid price data to display")
        except Exception as e:
            st.error(f"Error generating price distribution: {e}")
        
        # Product table
        st.subheader("Products")
        st.dataframe(df)
    else:
        st.info("No product data available. Generate feeds to see product analytics.")

with tab2:
    st.subheader("Feed Preview")
    
    # Feed URLs
    st.markdown(f"""
    ### Feed URLs
    
    Use these URLs in Google Merchant Center and Meta Business Manager:
    
    - **Google Shopping Feed (XML):**  
    `https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/feeds/google_shopping_feed.xml`
    
    - **Meta Shopping Feed (XML):**  
    `https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/feeds/meta_shopping_feed.xml`
    
    - **CSV Feed:**  
    `https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/feeds/google_shopping_feed.csv`
    """)
    
    # Display feed sample
    if not df.empty:
        st.subheader("Sample Product Data")
        st.dataframe(df.head(5))
    else:
        st.warning("No feed data available yet")
    
    # XML preview
    st.subheader("XML Feed Preview")
    xml_content = get_github_file("feeds/google_shopping_feed.xml")
    if xml_content:
        st.code(xml_content[:2000] + "..." if len(xml_content) > 2000 else xml_content, language="xml")
    else:
        st.warning("XML feed not found or not generated yet")

# Footer
st.markdown("---")
st.markdown(
    f"Made with ❤️ for JoyAndCo | Dashboard Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
)
