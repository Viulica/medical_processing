import os
import tempfile
import zipfile
import shutil
from pathlib import Path
import pandas as pd

def extract_group_name_from_excel(excel_file):
    """
    Extract the group name from the Excel filename (e.g., 'DUN.xlsx' -> 'DUN')
    """
    filename = excel_file.name
    # Remove extension and get the base name
    group_name = Path(filename).stem
    return group_name

def process_uploaded_files(uploaded_patient_file, uploaded_excel_file):
    """
    Process uploaded files and prepare them for extraction.
    
    Args:
        uploaded_patient_file: StreamlitUploadedFile - PDF or ZIP file
        uploaded_excel_file: StreamlitUploadedFile - XLSX file with field definitions
    
    Returns:
        tuple: (temp_directory_path, group_name)
    """
    # Create temporary directory for processing
    temp_dir = tempfile.mkdtemp()
    
    # Extract group name from Excel file
    group_name = extract_group_name_from_excel(uploaded_excel_file)
    
    # Save Excel file to temporary directory
    excel_path = os.path.join(temp_dir, "instructions", uploaded_excel_file.name)
    os.makedirs(os.path.dirname(excel_path), exist_ok=True)
    
    with open(excel_path, 'wb') as f:
        f.write(uploaded_excel_file.getvalue())
    
    # Process patient documents based on file type
    if uploaded_patient_file.name.lower().endswith('.zip'):
        # Handle ZIP file - extract PDFs directly to output folder
        process_zip_file(uploaded_patient_file, temp_dir)
    else:
        # Handle single PDF - save to input folder for splitting
        process_single_pdf(uploaded_patient_file, temp_dir)
    
    return temp_dir, group_name

def process_zip_file(uploaded_file, temp_dir):
    """
    Extract PDFs from ZIP file and place them in output folder.
    """
    # Create output directory
    output_dir = os.path.join(temp_dir, "output")
    os.makedirs(output_dir, exist_ok=True)
    
    # Extract ZIP file
    with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
        # List all files in ZIP
        file_list = zip_ref.namelist()
        
        # Extract only PDF files
        pdf_files = [f for f in file_list if f.lower().endswith('.pdf')]
        
        if not pdf_files:
            raise ValueError("No PDF files found in the ZIP archive")
        
        # Extract PDFs to output directory
        for pdf_file in pdf_files:
            zip_ref.extract(pdf_file, output_dir)
            
            # If the PDF was in a subdirectory, move it to the root of output
            if '/' in pdf_file:
                old_path = os.path.join(output_dir, pdf_file)
                new_path = os.path.join(output_dir, os.path.basename(pdf_file))
                shutil.move(old_path, new_path)
                
                # Remove empty subdirectories
                subdir = os.path.dirname(os.path.join(output_dir, pdf_file))
                if os.path.exists(subdir) and not os.listdir(subdir):
                    os.rmdir(subdir)

def process_single_pdf(uploaded_file, temp_dir):
    """
    Save single PDF to input folder for processing by split_pdf_by_detections.py
    """
    # Create input directory
    input_dir = os.path.join(temp_dir, "input")
    os.makedirs(input_dir, exist_ok=True)
    
    # Save PDF to input directory
    pdf_path = os.path.join(input_dir, uploaded_file.name)
    with open(pdf_path, 'wb') as f:
        f.write(uploaded_file.getvalue())
    
    # Create output directory
    output_dir = os.path.join(temp_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

def cleanup_temp_directory(temp_dir):
    """
    Clean up temporary directory and all its contents.
    """
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True) 