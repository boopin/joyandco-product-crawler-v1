import streamlit as st
import pandas as pd
import plotly.express as px
import subprocess
import os
import glob
import xml.etree.ElementTree as ET
import json
from datetime import datetime
import time

st.set_page_config(
    page_title="JoyAndCo Product Feed Generator",
    page_icon="🛒",
    layout="wide"
)

st.title("JoyAndCo Product Feed Generator")
st.markdown("Monitor and control product feeds for Google and Meta shopping ads")

# Sidebar
st.sidebar.header("Controls")

# Manual feed generation
if st.sidebar.button("🔄 Generate Feeds Now", help="Run the crawler and generate fresh feeds"):
    with st.spinner("Crawling products and generating feeds..."):
        try:
            process = subprocess.Popen(
                ["python", "crawler.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Create a placeholder for live output
            output_placeholder = st.empty()
            
            # Stream the output
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    output_placeholder.text(output.strip())
            
            returncode = process.poll()
            
            if returncode == 0:
                st.success("✅ Feed generation completed successfully!")
                time.sleep(2)  # Give time to read the message
                st.rerun()  # Refresh the page to show new data
            else:
                st.error("❌ Feed generation failed. Check the logs below.")
                error_output = process.stderr.read()
                st.code(error_output)
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

# Main content area
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "🔍 Feed Preview", "📝 Logs"])

with tab1:
    col1, col2, col3 = st.columns(3)
    
    # Check for feed files
    feed_files = glob.glob("feeds/*.*")
    last_updated = None
    if feed_files:
        last_updated = max([os.path.getmtime(file) for file in feed_files])
        last_updated = datetime.fromtimestamp(last_updated)
    
    with col1:
        st.metric(
            label="Google Feed Status", 
            value="Active" if any("google" in file for file in feed_files) else "Not Generated"
        )
        if last_updated:
            st.caption(f"Last updated: {last_updated.strftime('%Y-%m-%d %H:%M:%S')}")
    
    with col2:
        st.metric(
            label="Meta Feed Status", 
            value="Active" if any("meta" in file for file in feed_files) else "Not Generated"
        )
    
    with col3:
        product_count = 0
        csv_file = "feeds/google_shopping_feed.csv"
        if os.path.exists(csv_file):
            df = pd.read_csv(csv_file)
            product_count = len(df)
        
        st.metric(label="Total Products", value=product_count)
    
    # Product data visualization
    st.subheader("Product Data")
    
    if os.path.exists(csv_file) and product_count > 0:
        df = pd.read_csv(csv_file)
        
        # Price distribution
        if 'price' in df.columns:
            st.subheader("Price Distribution")
            fig = px.histogram(df, x="price", nbins=20, title="Product Price Distribution")
            st.plotly_chart(fig, use_container_width=True)
        
        # Product availability
        if 'availability' in df.columns:
            st.subheader("Product Availability")
            availability_counts = df['availability'].value_counts().reset_index()
            availability_counts.columns = ['Status', 'Count']
            fig = px.pie(availability_counts, values='Count', names='Status', title="Product Availability")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No product data available. Generate feeds to see product analytics.")

with tab2:
    st.subheader("Feed Preview")
    
    feed_type = st.selectbox(
        "Select Feed Type",
        options=["Google Shopping (XML)", "Meta Shopping (XML)", "CSV Feed"]
    )
    
    if feed_type == "Google Shopping (XML)":
        xml_file = "feeds/google_shopping_feed.xml"
        if os.path.exists(xml_file):
            with open(xml_file, 'r') as f:
                xml_content = f.read()
            st.code(xml_content[:5000] + "..." if len(xml_content) > 5000 else xml_content, language="xml")
            
            # Display structured data
            try:
                tree = ET.parse(xml_file)
                root = tree.getroot()
                items = root.findall('.//item')
                
                if items:
                    st.subheader(f"Products in Feed: {len(items)}")
                    sample_item = items[0]
                    st.json({child.tag.split('}')[-1]: child.text for child in sample_item})
            except Exception as e:
                st.error(f"Error parsing XML: {str(e)}")
        else:
            st.warning("Google Shopping feed has not been generated yet.")
    
    elif feed_type == "Meta Shopping (XML)":
        xml_file = "feeds/meta_shopping_feed.xml"
        if os.path.exists(xml_file):
            with open(xml_file, 'r') as f:
                xml_content = f.read()
            st.code(xml_content[:5000] + "..." if len(xml_content) > 5000 else xml_content, language="xml")
            
            # Display structured data
            try:
                tree = ET.parse(xml_file)
                root = tree.getroot()
                items = root.findall('.//item')
                
                if items:
                    st.subheader(f"Products in Feed: {len(items)}")
                    sample_item = items[0]
                    st.json({child.tag: child.text for child in sample_item})
            except Exception as e:
                st.error(f"Error parsing XML: {str(e)}")
        else:
            st.warning("Meta Shopping feed has not been generated yet.")
    
    else:  # CSV Feed
        csv_file = "feeds/google_shopping_feed.csv"
        if os.path.exists(csv_file):
            df = pd.read_csv(csv_file)
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("CSV feed has not been generated yet.")

with tab3:
    st.subheader("Crawler Logs")
    
    # Check if log file exists and display it
    log_file = "crawler.log"
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            log_content = f.readlines()
        
        # Display the most recent logs first (last 100 lines)
        st.code(''.join(log_content[-100:]), language="bash")
        
        if st.button("Clear Logs"):
            with open(log_file, 'w') as f:
                f.write("")
            st.success("Logs cleared successfully")
            time.sleep(1)
            st.rerun()
    else:
        st.info("No logs available. Run the crawler to generate logs.")

# Footer
st.markdown("---")
st.markdown(
    "Made with ❤️ for JoyAndCo | Last Dashboard Update: " + 
    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
)
