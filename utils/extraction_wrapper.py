import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path
import pandas as pd

def run_extraction_pipeline(temp_dir, group_name):
    """
    Run the complete extraction pipeline using existing scripts.
    
    Args:
        temp_dir: Path to temporary directory with processed files
        group_name: Name of the group (e.g., 'DUN') for configuration
    
    Returns:
        str: Path to the output CSV file
    """
    # Get the current script directory
    current_dir = os.path.join(os.path.dirname(__file__), '..', 'current')
    
    # Check if we need to run the PDF splitting script
    input_dir = os.path.join(temp_dir, "input")
    output_dir = os.path.join(temp_dir, "output")
    
    if os.path.exists(input_dir) and os.listdir(input_dir):
        # We have a single PDF that needs splitting
        print(f"Running PDF splitting for {group_name}...")
        run_pdf_splitting(current_dir, temp_dir, group_name)
    
    # Run the extraction script
    print(f"Running data extraction for {group_name}...")
    output_csv_path = run_data_extraction(current_dir, temp_dir, group_name)
    
    return output_csv_path

def run_pdf_splitting(current_dir, temp_dir, group_name):
    """
    Run the PDF splitting script with appropriate configuration.
    """
    # Get filter strings for the group
    filter_strings = get_filter_strings_for_group(group_name)
    
    # Copy necessary files to temp directory
    copy_required_files(current_dir, temp_dir)
    
    # Import and run the lightweight splitting script directly
    try:
        print(f"Running PDF splitting script with:")
        print(f"  Input folder: {os.path.join(temp_dir, 'input')}")
        print(f"  Output folder: {os.path.join(temp_dir, 'output')}")
        print(f"  Filter strings: {filter_strings}")
        print(f"  Working directory: {temp_dir}")
        
        # Add current directory to Python path
        sys.path.insert(0, current_dir)
        
        # Import the original OCR-based splitting function
        from current.split_pdf_by_detections_ocr import split_pdf_by_detections
        
        # Run the splitting
        input_folder = os.path.join(temp_dir, "input")
        output_folder = os.path.join(temp_dir, "output")
        
        split_pdf_by_detections(input_folder, output_folder, filter_strings, case_sensitive=False)
        
        # Check if PDFs were actually created
        if os.path.exists(output_folder):
            pdf_files = [f for f in os.listdir(output_folder) if f.endswith('.pdf')]
            if pdf_files:
                print(f"✅ Successfully created {len(pdf_files)} split PDF files")
            else:
                print(f"❌ No PDF files found in output directory after splitting")
                # List contents of input and output directories for debugging
                input_dir = os.path.join(temp_dir, "input")
                print(f"Input directory contents: {os.listdir(input_dir) if os.path.exists(input_dir) else 'Not found'}")
                print(f"Output directory contents: {os.listdir(output_folder)}")
                raise Exception("PDF splitting completed but no PDF files were created")
        else:
            raise Exception("Output directory was not created by splitting script")
            
    except Exception as e:
        raise Exception(f"Error running PDF splitting: {str(e)}")

def run_data_extraction(current_dir, temp_dir, group_name):
    """
    Run the data extraction script.
    """
    # Paths for the extraction script
    output_folder = os.path.join(temp_dir, "output")
    instructions_file = os.path.join(temp_dir, "instructions", f"{group_name}.xlsx")
    
    # Create a temporary script for extraction
    script_content = create_extraction_script(output_folder, instructions_file)
    
    # Save the script to a temporary file
    script_path = os.path.join(temp_dir, "temp_extract_script.py")
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    # Copy necessary files to temp directory
    copy_required_files(current_dir, temp_dir)
    
    # Run the script
    try:
        print(f"Running extraction script with:")
        print(f"  Output folder: {output_folder}")
        print(f"  Instructions file: {instructions_file}")
        print(f"  Working directory: {temp_dir}")
        
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=temp_dir,  # Run from temp directory
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        # Print stdout and stderr for debugging
        print(f"Script stdout: {result.stdout}")
        if result.stderr:
            print(f"Script stderr: {result.stderr}")
        
        if result.returncode != 0:
            raise Exception(f"Data extraction failed with return code {result.returncode}: {result.stderr}")
        
        # Look for the output CSV file
        output_csv_path = find_output_csv(temp_dir)
        if not output_csv_path:
            # List all files in temp directory for debugging
            print(f"Files in temp directory:")
            for root, dirs, files in os.walk(temp_dir):
                level = root.replace(temp_dir, '').count(os.sep)
                indent = ' ' * 2 * level
                print(f"{indent}{os.path.basename(root)}/")
                subindent = ' ' * 2 * (level + 1)
                for file in files:
                    print(f"{subindent}{file}")
            
            raise Exception("No output CSV file found after extraction")
            
        return output_csv_path
        
    except subprocess.TimeoutExpired:
        raise Exception("Data extraction timed out after 10 minutes")
    except Exception as e:
        raise Exception(f"Error running data extraction: {str(e)}")

def copy_required_files(current_dir, temp_dir):
    """
    Copy required files to the temporary directory so scripts can find them.
    """
    required_files = [
        "field_definitions.py",
        "extraction_prompt.txt"
    ]
    
    for file_name in required_files:
        source_path = os.path.join(current_dir, file_name)
        dest_path = os.path.join(temp_dir, file_name)
        
        if os.path.exists(source_path):
            shutil.copy2(source_path, dest_path)

def get_filter_strings_for_group(group_name):
    """
    Get the appropriate filter strings for the given group.
    """
    filter_strings_map = {
        'DUN': ['Patient Address'],
        'SIO': ['Anesthesia Billing', 'Address 1', 'Address 2', 'Gender'],
        'SIO-STL': ['Patient Demographics'],
        'STA-DGSS': ['Patient Demographics Form'],
        'APO-UTP': ['Billing and Compliance Report'],
        'APO-UPM': ['Billing and Compliance Report'],
        'APO-UTP-v2': ['Patient Demographics'],
        'APO-CVO': ['Patient Registration Data'],
        'GAP-UMSC': ['Patient Registration Data'],
        'KAP-CYP': ['Patent Demographic Form'],
        'KAP-ASC': ['PatientData'],
        'WPA': ['Anesthesia Billing', 'Address 1', 'Address 2', 'Gender']
    }
    
    # Try exact match first
    if group_name in filter_strings_map:
        return filter_strings_map[group_name]
    
    # Try partial matches
    for key, value in filter_strings_map.items():
        if group_name.upper() in key.upper() or key.upper() in group_name.upper():
            return value
    
    # Default to DUN if no match found
    return filter_strings_map['DUN']

def create_splitting_script(filter_strings, temp_dir):
    """
    Create a temporary splitting script with the correct filter strings.
    """
    script_content = f'''#!/usr/bin/env python3
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(__file__))

# Import the OCR-based splitting script
from current.split_pdf_by_detections_ocr import split_pdf_by_detections

# Set up paths
input_folder = os.path.join("{temp_dir}", "input")
output_folder = os.path.join("{temp_dir}", "output")

# Filter strings
filter_strings = {filter_strings}

# Run splitting
split_pdf_by_detections(input_folder, output_folder, filter_strings, case_sensitive=False)
'''
    return script_content

def create_extraction_script(output_folder, instructions_file):
    """
    Create a temporary extraction script with the correct parameters.
    """
    # Read the original script
    current_dir = os.path.join(os.path.dirname(__file__), '..', 'current')
    original_script_path = os.path.join(current_dir, "extract_info.py")
    
    with open(original_script_path, 'r') as f:
        original_content = f.read()
    
    # Add our configuration at the beginning to override the defaults
    config_section = f'''# ============================================================================
# CONFIGURATION - Auto-generated by Streamlit app
# ============================================================================

# Override the default values for command line arguments
import sys
if len(sys.argv) == 1:  # Only if no arguments provided
    sys.argv = [
        sys.argv[0],  # Script name
        "{output_folder}",  # input_folder
        "{instructions_file}",  # excel_file
        "2",  # n_pages
        "14"  # max_workers
    ]

# ============================================================================
# END CONFIGURATION
# ============================================================================

'''
    
    return config_section + original_content

def find_output_csv(temp_dir):
    """
    Find the output CSV file in the temporary directory.
    The extraction script creates CSV files in the 'extracted' folder.
    """
    # First look in the extracted folder (where the script creates the CSV)
    extracted_dir = os.path.join(temp_dir, "extracted")
    if os.path.exists(extracted_dir):
        for file in os.listdir(extracted_dir):
            if file.endswith('.csv'):
                return os.path.join(extracted_dir, file)
    
    # If not found in extracted folder, look in the temp directory and subdirectories
    for root, dirs, files in os.walk(temp_dir):
        for file in files:
            if file.endswith('.csv'):
                return os.path.join(root, file)
    
    return None 