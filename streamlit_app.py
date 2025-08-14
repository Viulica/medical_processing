import streamlit as st
import os
import tempfile
import zipfile
import shutil
from datetime import datetime
import pandas as pd
from pathlib import Path
import sys
import psutil
import gc

# Add current directory to path so we can import the existing scripts
sys.path.append(os.path.join(os.path.dirname(__file__), 'current'))

from utils.file_processor import process_uploaded_files
from utils.extraction_wrapper import run_extraction_pipeline

# Check for required environment variables
if 'GOOGLE_API_KEY' not in os.environ:
    st.error("""
    ❌ **Missing Google API Key**
    
    Please set the `GOOGLE_API_KEY` environment variable in your deployment platform.
    
    **How to fix:**
    1. Go to your deployment platform settings
    2. Add environment variable: `GOOGLE_API_KEY`
    3. Set the value to your Google Generative AI API key
    4. Redeploy your app
    """)
    st.stop()

# Resource monitoring
def check_memory_usage():
    """Check if we're running low on memory"""
    memory = psutil.virtual_memory()
    if memory.percent > 80:
        st.warning(f"⚠️ High memory usage: {memory.percent}%. Consider restarting the app.")
        gc.collect()  # Force garbage collection
    return memory.percent

# Page configuration
st.set_page_config(
    page_title="Medical Document Processor",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for professional styling
st.markdown("""
<style>
    /* Hide ALL default Streamlit elements */
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    header {visibility: hidden !important;}
    
    /* Hide the tabs and navigation completely */
    .stTabs {display: none !important;}
    [data-testid="stSidebar"] {display: none !important;}
    
    /* Hide any other default elements */
    .stDeployButton {display: none !important;}
    .stApp > header {display: none !important;}
    .stApp > footer {display: none !important;}
    
    /* Remove any padding/margins from the top */
    .main .block-container {padding-top: 1rem !important;}
    
    .main-header {
        font-size: 2rem;
        font-weight: 600;
        color: #262730;
        text-align: center;
        margin-bottom: 1.5rem;
        border-bottom: 2px solid #e0e0e0;
        padding-bottom: 0.5rem;
    }
    .upload-section {
        background-color: #f8f9fa;
        padding: 1.25rem;
        border-radius: 6px;
        border: 1px solid #e9ecef;
        margin: 0.75rem 0;
    }
    .success-message {
        background-color: #d1ecf1;
        color: #0c5460;
        padding: 0.75rem;
        border-radius: 4px;
        border: 1px solid #bee5eb;
    }
    .error-message {
        background-color: #f8d7da;
        color: #721c24;
        padding: 0.75rem;
        border-radius: 4px;
        border: 1px solid #f5c6cb;
    }
    .section-header {
        font-size: 1.1rem;
        font-weight: 500;
        color: #262730;
        margin-bottom: 0.5rem;
    }
    .file-info {
        background-color: #e9ecef;
        padding: 0.5rem;
        border-radius: 4px;
        font-size: 0.9rem;
        color: #495057;
    }
</style>
""", unsafe_allow_html=True)

def main():
    # Initialize session state
    if 'uploaded_files' not in st.session_state:
        st.session_state.uploaded_files = {}
    
    # Header
    st.markdown('<h1 class="main-header">Medical Document Processor</h1>', unsafe_allow_html=True)
    
    # Sidebar for instructions
    with st.sidebar:
        st.header("Instructions")
        st.markdown("""
        1. **Upload Patient Documents**: PDF or ZIP file
        2. **Upload Field Definitions**: XLSX file (e.g., DUN.xlsx)
        3. **Click Process** to extract data
        4. **Download** the resulting CSV file
        """)
        
        st.header("Supported Formats")
        st.markdown("""
        - **Patient Documents**: PDF, ZIP
        - **Field Definitions**: XLSX
        - **Output**: CSV
        """)
        
        # Add reset button
        if st.button("🔄 Reset App"):
            st.session_state.uploaded_files = {}
            st.rerun()
    
    # Main content area
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown('<div class="upload-section">', unsafe_allow_html=True)
        st.markdown('<div class="section-header">Upload Patient Documents</div>', unsafe_allow_html=True)
        
        # Use key to force re-render
        uploaded_patient_file = st.file_uploader(
            "Choose a PDF or ZIP file",
            type=['pdf', 'zip'],
            key="patient_file_uploader",
            help="Upload a single PDF with multiple patients or a ZIP file containing individual patient PDFs"
        )
        
        # Alternative upload method for PDFs
        if uploaded_patient_file is None:
            st.info("If PDF upload doesn't work, try this alternative:")
            alt_upload = st.file_uploader(
                "Alternative PDF upload",
                type=['pdf', 'zip'],
                key="alt_patient_uploader",
                help="Alternative upload method"
            )
            if alt_upload:
                uploaded_patient_file = alt_upload
                st.success("✅ PDF uploaded via alternative method!")
        
        if uploaded_patient_file:
            try:
                file_size = len(uploaded_patient_file.getvalue()) / (1024 * 1024)  # MB
                st.markdown(f'<div class="file-info">File: {uploaded_patient_file.name} ({file_size:.1f} MB)</div>', unsafe_allow_html=True)
                # Store in session state
                st.session_state.uploaded_files['patient'] = uploaded_patient_file
                st.success(f"✅ Successfully loaded: {uploaded_patient_file.name}")
            except Exception as e:
                st.error(f"❌ Error reading file: {str(e)}")
                uploaded_patient_file = None
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="upload-section">', unsafe_allow_html=True)
        st.markdown('<div class="section-header">Upload Field Definitions</div>', unsafe_allow_html=True)
        
        uploaded_excel_file = st.file_uploader(
            "Choose an XLSX file",
            type=['xlsx'],
            key="excel_file_uploader",
            help="Upload the Excel file containing field definitions (e.g., DUN.xlsx)"
        )
        
        if uploaded_excel_file:
            st.markdown(f'<div class="file-info">File: {uploaded_excel_file.name}</div>', unsafe_allow_html=True)
            # Store in session state
            st.session_state.uploaded_files['excel'] = uploaded_excel_file
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Process button
    st.markdown("---")
    
    # Fallback to session state if uploader is buggy
    if uploaded_patient_file is None and 'patient' in st.session_state.uploaded_files:
        uploaded_patient_file = st.session_state.uploaded_files['patient']
        st.info("📁 Using patient file from session state")
        
    if uploaded_excel_file is None and 'excel' in st.session_state.uploaded_files:
        uploaded_excel_file = st.session_state.uploaded_files['excel']
        st.info("📊 Using excel file from session state")
    
    if st.button("Process Documents", type="primary"):
        if not uploaded_patient_file or not uploaded_excel_file:
            st.error("Please upload both a patient document file and a field definitions file.")
            return
        
        # Validate uploaded files
        try:
            # Test if we can read the files
            patient_data = uploaded_patient_file.getvalue()
            excel_data = uploaded_excel_file.getvalue()
            
            if len(patient_data) == 0:
                st.error("Patient file appears to be empty. Please try uploading again.")
                return
                
            if len(excel_data) == 0:
                st.error("Excel file appears to be empty. Please try uploading again.")
                return
            
            # Check file size for PDF
            if uploaded_patient_file.name.lower().endswith('.pdf'):
                file_size_mb = len(patient_data) / (1024 * 1024)
                if file_size_mb > 50:
                    st.warning(f"⚠️ Large PDF detected ({file_size_mb:.1f} MB). This might take longer to process.")
                
                # Validate PDF header
                if not patient_data.startswith(b'%PDF'):
                    st.error("❌ Invalid PDF file - doesn't start with PDF header")
                    return
                
            st.success("✅ Files validated successfully!")
            
        except Exception as e:
            st.error(f"Error reading uploaded files: {str(e)}")
            return
        
        # Show processing status
        with st.spinner("Processing documents..."):
            try:
                # Check memory before processing
                memory_usage = check_memory_usage()
                st.info(f"Memory usage: {memory_usage}%")
                
                # Create progress bar
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Step 1: Process uploaded files
                status_text.text("Processing uploaded files...")
                progress_bar.progress(20)
                
                # Process files without signal timeout (Streamlit doesn't support it)
                try:
                    temp_dir, group_name = process_uploaded_files(
                        uploaded_patient_file, 
                        uploaded_excel_file
                    )
                except Exception as e:
                    st.error(f"❌ Error processing files: {str(e)}")
                    return
                
                # Step 2: Run extraction pipeline
                status_text.text("Extracting data from documents...")
                progress_bar.progress(50)
                
                try:
                    output_csv_path = run_extraction_pipeline(temp_dir, group_name)
                except Exception as e:
                    st.error(f"❌ Error during extraction: {str(e)}")
                    return
                
                # Step 3: Prepare for download
                status_text.text("Preparing results...")
                progress_bar.progress(90)
                
                # Read the CSV file for download
                with open(output_csv_path, 'r') as f:
                    csv_data = f.read()
                
                # Generate filename based on original uploaded file
                original_filename = uploaded_patient_file.name
                # Replace .pdf or .zip extension with .csv
                if original_filename.lower().endswith('.pdf'):
                    download_filename = original_filename[:-4] + '.csv'
                elif original_filename.lower().endswith('.zip'):
                    download_filename = original_filename[:-4] + '.csv'
                else:
                    # Fallback to original naming if file type is unexpected
                    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
                    download_filename = f"{group_name}_extracted_data_{timestamp}.csv"
                
                progress_bar.progress(100)
                status_text.text("Processing complete!")
                
                # Success message
                st.markdown('<div class="success-message">', unsafe_allow_html=True)
                st.success(f"Successfully processed {group_name} documents!")
                st.markdown('</div>', unsafe_allow_html=True)
                
                # Download button
                st.download_button(
                    label="Download CSV Results",
                    data=csv_data,
                    file_name=download_filename,
                    mime="text/csv",
                    use_container_width=True
                )
                
                # Show preview of results
                st.header("Results Preview")
                df = pd.read_csv(output_csv_path)
                st.dataframe(df.head(10), use_container_width=True)
                st.info(f"Total records extracted: {len(df)}")
                
            except Exception as e:
                st.markdown('<div class="error-message">', unsafe_allow_html=True)
                st.error(f"Error during processing: {str(e)}")
                st.markdown('</div>', unsafe_allow_html=True)
                st.exception(e)
            finally:
                # Cleanup temporary directory
                if 'temp_dir' in locals():
                    shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    main() 