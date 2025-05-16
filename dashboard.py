import streamlit as st
import pandas as pd
import plotly.express as px
import os
import glob
import xml.etree.ElementTree as ET
from datetime import datetime
import requests

st.set_page_config(
    page_title="JoyAndCo Product Feed Generator",
    page_icon="🛒",
    layout="wide"
)

st.title("JoyAndCo Product Feed Generator")
st.markdown("Monitor and control product feeds for Google and Meta shopping ads")

# Check GitHub for feed files
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_github_feed_data():
    # Replace with your GitHub repo details
    owner = "your-username"
    repo = "joyandco-product-feed"
    
    # Get CSV feed content
    csv_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/feeds/google_shopping_feed.csv"
    try:
        df = pd.read_csv(csv_url)
        return df
    except:
        st.warning("Could not load feed data from GitHub")
        return pd.DataFrame()
    
# Get GitHub Actions status
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_github_actions_status():
    # Replace with your repo details
    owner = "your-username"
    repo = "joyandco-product-feed"
    
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            runs = response.json()["workflow_runs"]
            if runs:
                latest_run = runs[0]
                return {
                    "status": latest_run["conclusion"] or "running",
                    "time": latest_run["updated_at"],
                    "url": latest_run["html_url"]
                }
    except:
        pass
    return None

# Main content
st.sidebar.header("Controls")

# Link to manually trigger GitHub Actions
st.sidebar.markdown("""
## Manual Feed Generation
The crawler runs daily via GitHub Actions.

To manually trigger a new feed generation:
1. [Go to Actions on GitHub](https://github.com/your-username/joyandco-product-feed/actions)
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
    
    # Feed data
    df = get_github_feed_data()
    
    # Display metrics
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Total Products", len(df) if not df.empty else 0)
    
    with col2:
        st.metric("Feed Status", "Active" if not df.empty else "Not Generated")
    
    # Price distribution
    if not df.empty and 'price' in df.columns:
        st.subheader("Price Distribution")
        fig = px.histogram(df, x="price", nbins=20, title="Product Price Distribution")
        st.plotly_chart(fig, use_container_width=True)
        
        # Product table
        st.subheader("Products")
        st.dataframe(df)

with tab2:
    st.subheader("Feed Preview")
    
    # Feed URLs
    st.markdown("""
    ### Feed URLs
    
    Use these URLs in Google Merchant Center and Meta Business Manager:
    
    - **Google Shopping Feed (XML):**  
    `https://raw.githubusercontent.com/your-username/joyandco-product-feed/main/feeds/google_shopping_feed.xml`
    
    - **Meta Shopping Feed (XML):**  
    `https://raw.githubusercontent.com/your-username/joyandco-product-feed/main/feeds/meta_shopping_feed.xml`
    
    - **CSV Feed:**  
    `https://raw.githubusercontent.com/your-username/joyandco-product-feed/main/feeds/google_shopping_feed.csv`
    """)
    
    # Display feed sample
    if not df.empty:
        st.subheader("Sample Product Data")
        st.dataframe(df.head(5))

# Footer
st.markdown("---")
st.markdown(
    "Made with ❤️ for JoyAndCo | Dashboard Last Updated: " + 
    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
)
