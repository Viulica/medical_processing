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
    # Create a temporary script that sets the correct filter strings
    filter_strings = get_filter_strings_for_group(group_name)
    
    # Create a modified version of the splitting script
    script_content = create_splitting_script(filter_strings, temp_dir)
    
    # Save the script to a temporary file
    script_path = os.path.join(temp_dir, "temp_split_script.py")
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    # Copy necessary files to temp directory
    copy_required_files(current_dir, temp_dir)
    
    # Run the script
    try:
        print(f"Running PDF splitting script with:")
        print(f"  Input folder: {os.path.join(temp_dir, 'input')}")
        print(f"  Output folder: {os.path.join(temp_dir, 'output')}")
        print(f"  Filter strings: {filter_strings}")
        print(f"  Working directory: {temp_dir}")
        
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=temp_dir,  # Run from temp directory
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        # Print stdout and stderr for debugging
        print(f"Splitting script stdout: {result.stdout}")
        if result.stderr:
            print(f"Splitting script stderr: {result.stderr}")
        
        if result.returncode != 0:
            raise Exception(f"PDF splitting failed with return code {result.returncode}: {result.stderr}")
        
        # Check if PDFs were actually created
        output_dir = os.path.join(temp_dir, "output")
        if os.path.exists(output_dir):
            pdf_files = [f for f in os.listdir(output_dir) if f.endswith('.pdf')]
            if pdf_files:
                print(f"✅ Successfully created {len(pdf_files)} split PDF files")
            else:
                print(f"❌ No PDF files found in output directory after splitting")
                # List contents of input and output directories for debugging
                input_dir = os.path.join(temp_dir, "input")
                print(f"Input directory contents: {os.listdir(input_dir) if os.path.exists(input_dir) else 'Not found'}")
                print(f"Output directory contents: {os.listdir(output_dir)}")
                raise Exception("PDF splitting completed but no PDF files were created")
        else:
            raise Exception("Output directory was not created by splitting script")
            
    except subprocess.TimeoutExpired:
        raise Exception("PDF splitting timed out after 5 minutes")
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
    Create a temporary splitting script with the correct configuration.
    """
    # Read the original script
    current_dir = os.path.join(os.path.dirname(__file__), '..', 'current')
    original_script_path = os.path.join(current_dir, "1-split_pdf_by_detections.py")
    
    with open(original_script_path, 'r') as f:
        original_content = f.read()
    
    # Replace the configuration section
    config_section = f'''# ============================================================================
# CONFIGURATION - Auto-generated by Streamlit app
# ============================================================================

# Filter strings - ALL of these must be present on a page to keep it (AND logic)
WPA_FILTER_STRINGS = {filter_strings}

SIO_PSS_FILTER_STRINGS = {filter_strings}

SIO_STL_FILTER_STRINGS = {filter_strings}

STA_DGSS_FILTER_STRINGS = {filter_strings}
 
DUN_FILTER_STRINGS = {filter_strings}

APO_UTP_FILTER_STRINGS = {filter_strings}

APO_UPM_FILTER_STRINGS = {filter_strings}

APO_UTP_v2_FILTER_STRINGS = {filter_strings}

APO_CVO_FILTER_STRINGS = {filter_strings}

GAP_UMSC_FILTER_STRINGS = {filter_strings}

KAP_CYP_FILTER_STRINGS = {filter_strings}

KAP_ASC_FILTER_STRINGS = {filter_strings}

# Choose which filter to use
FILTER_STRINGS = {filter_strings}

# Folder settings
INPUT_FOLDER = "input"          # Folder containing PDF files to process
OUTPUT_FOLDER = "output"        # Folder where split PDFs will be saved

# Processing settings
CASE_SENSITIVE = False          # Set to True for case-sensitive matching
PAGE_WORKERS = None             # Number of threads for processing pages (None = auto)
PDF_WORKERS = None              # Number of threads for processing PDFs (None = auto)

# Single file processing (set to None to process entire folder)
SINGLE_FILE = None              # e.g., "path/to/specific/file.pdf" or None

# ============================================================================
# END CONFIGURATION
# ============================================================================

'''
    
    # Find where the configuration section ends and the imports begin
    import_start = original_content.find("import os")
    if import_start == -1:
        import_start = original_content.find("import sys")
    
    if import_start == -1:
        # If we can't find imports, just append the config at the beginning
        return config_section + original_content
    
    # Replace everything from the start to the imports with our config
    modified_content = config_section + original_content[import_start:]
    
    return modified_content

def create_extraction_script(output_folder, instructions_file):
    """
    Create a temporary extraction script with the correct parameters.
    """
    # Read the original script
    current_dir = os.path.join(os.path.dirname(__file__), '..', 'current')
    original_script_path = os.path.join(current_dir, "2-extract_info.py")
    
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