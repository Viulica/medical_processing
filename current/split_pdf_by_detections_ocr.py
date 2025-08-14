# ============================================================================
# CONFIGURATION - Edit these variables to customize the filtering
# ============================================================================

# Filter strings - ALL of these must be present on a page to keep it (AND logic)
WPA_FILTER_STRINGS = [
    "Anesthesia Billing",
    "Address 1", 
    "Address 2",
    "Gender"
]

SIO_PSS_FILTER_STRINGS = [
    "Anesthesia Billing",
    "Address 1", 
    "Address 2",
    "Gender"
]

SIO_STL_FILTER_STRINGS = [
    "Patient Demographics"
]

STA_DGSS_FILTER_STRINGS = [
    "Patient Demographics Form",
]
 
DUN_FILTER_STRINGS = [
    "Patient Address"
]

APO_UTP_FILTER_STRINGS = [
    "Billing and Compliance Report"
]

APO_UPM_FILTER_STRINGS = [
    "Billing and Compliance Report"
]

APO_UTP_v2_FILTER_STRINGS = [
    "Patient Demographics"
]

APO_CVO_FILTER_STRINGS = [
    "Patient Registration Data"
]

GAP_UMSC_FILTER_STRINGS = [
    "Patient Registration Data",
]

KAP_CYP_FILTER_STRINGS = [
    "Patent Demographic Form"
]

KAP_ASC_FILTER_STRINGS = [
    "PatientData"
]

# Choose which filter to use
FILTER_STRINGS = DUN_FILTER_STRINGS

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

import os
import sys
import glob
import tempfile
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
import threading

# Thread-local storage for print synchronization
_print_lock = threading.Lock()

def thread_safe_print(*args, **kwargs):
    """Thread-safe print function to avoid interleaved output."""
    with _print_lock:
        print(*args, **kwargs)


def pdf_page_to_image(pdf_path, page_number, dpi=200):
    """Convert a PDF page to an image for OCR."""
    try:
        # Open the PDF
        doc = fitz.open(pdf_path)
        page = doc.load_page(page_number)
        
        # Convert to image
        mat = fitz.Matrix(dpi/72, dpi/72)  # Scale factor for DPI
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        
        # Convert to PIL Image
        image = Image.open(fitz.io.BytesIO(img_data))
        doc.close()
        
        return image
    except Exception as e:
        print(f"Error converting page {page_number} to image: {str(e)}")
        return None


def ocr_page(image):
    """Perform OCR on an image and return the text."""
    try:
        # Use pytesseract to extract text
        text = pytesseract.image_to_string(image, lang='eng')
        return text.strip()
    except Exception as e:
        print(f"Error performing OCR: {str(e)}")
        return ""


def check_page_contains_all_strings(pdf_path, page_number, filter_strings, case_sensitive=False):
    """Check if a PDF page contains ALL the specified filter strings (AND logic)."""
    try:
        # Convert page to image
        image = pdf_page_to_image(pdf_path, page_number)
        if not image:
            return False
        
        # Perform OCR
        page_text = ocr_page(image)
        
        # Check if ALL filter strings are present (AND logic)
        if not case_sensitive:
            page_text_lower = page_text.lower()
            return all(filter_string.lower() in page_text_lower for filter_string in filter_strings)
        else:
            return all(filter_string in page_text for filter_string in filter_strings)
            
    except Exception as e:
        print(f"Error checking page {page_number}: {str(e)}")
        return False


def check_page_contains_text_wrapper(args):
    """Wrapper function for check_page_contains_all_strings to work with ThreadPoolExecutor.map()"""
    pdf_path, page_number, filter_strings, case_sensitive = args
    return page_number, check_page_contains_all_strings(pdf_path, page_number, filter_strings, case_sensitive)


def find_detection_pages(input_pdf_path, filter_strings, case_sensitive=False, max_workers=None):
    """Find all pages that match the detection criteria."""
    try:
        reader = PdfReader(input_pdf_path)
        total_pages = len(reader.pages)
        
        filter_display = " AND ".join([f"'{s}'" for s in filter_strings])
        thread_safe_print(f"  Scanning {total_pages} pages for detections...")
        thread_safe_print(f"  Looking for pages containing: {filter_display}")
        
        # Prepare arguments for parallel processing
        page_args = [(input_pdf_path, page_num, filter_strings, case_sensitive) 
                     for page_num in range(total_pages)]
        
        # Process pages in parallel while maintaining order
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Use map to maintain order of results
            results = list(executor.map(check_page_contains_text_wrapper, page_args))
        
        # Find all detection pages
        detection_pages = []
        for page_num, contains_all_strings in results:
            thread_safe_print(f"    Page {page_num + 1}/{total_pages}...", end=" ")
            
            if contains_all_strings:
                detection_pages.append(page_num)
                thread_safe_print("✓ DETECTION")
            else:
                thread_safe_print("✗ no match")
        
        return detection_pages, total_pages
            
    except Exception as e:
        thread_safe_print(f"  Error scanning PDF: {str(e)}")
        return [], 0


def create_pdf_sections(input_pdf_path, output_folder, detection_pages, total_pages):
    """Create separate PDF files for each detected section."""
    try:
        reader = PdfReader(input_pdf_path)
        base_name = os.path.splitext(os.path.basename(input_pdf_path))[0]
        
        if not detection_pages:
            thread_safe_print("  No detections found - no PDFs created")
            return 0
        
        created_pdfs = 0
        
        # Create PDF sections
        for i, start_page in enumerate(detection_pages):
            # Determine end page (exclusive)
            if i + 1 < len(detection_pages):
                end_page = detection_pages[i + 1]  # Stop before next detection
            else:
                end_page = total_pages  # Last section goes to end
            
            # Create PDF for this section
            writer = PdfWriter()
            pages_in_section = end_page - start_page
            
            thread_safe_print(f"  Creating section {i + 1}: pages {start_page + 1}-{end_page} ({pages_in_section} pages)")
            
            # Add pages to this section
            for page_idx in range(start_page, end_page):
                writer.add_page(reader.pages[page_idx])
            
            # Save section PDF
            section_filename = f"{base_name}_section_{i + 1:02d}_pages_{start_page + 1}-{end_page}.pdf"
            section_path = os.path.join(output_folder, section_filename)
            
            with open(section_path, 'wb') as output_file:
                writer.write(output_file)
            
            thread_safe_print(f"    ✓ Saved {section_filename}")
            created_pdfs += 1
        
        return created_pdfs
        
    except Exception as e:
        thread_safe_print(f"  Error creating PDF sections: {str(e)}")
        return 0


def process_single_pdf(args):
    """Process a single PDF file - wrapper for use with ThreadPoolExecutor.map()"""
    pdf_file, output_folder, filter_strings, case_sensitive, max_workers = args
    
    thread_safe_print(f"\nProcessing: {os.path.basename(pdf_file)}")
    
    # Find detection pages
    detection_pages, total_pages = find_detection_pages(pdf_file, filter_strings, case_sensitive, max_workers)
    
    if detection_pages:
        thread_safe_print(f"  Found {len(detection_pages)} detections on pages: {[p+1 for p in detection_pages]}")
        # Create separate PDFs for each section
        created_count = create_pdf_sections(pdf_file, output_folder, detection_pages, total_pages)
        thread_safe_print(f"  ✓ Created {created_count} section PDFs")
        return created_count
    else:
        thread_safe_print(f"  ✗ No detections found in {os.path.basename(pdf_file)}")
        return 0


def process_input_folder(input_folder, output_folder, filter_strings, case_sensitive=False, max_workers=None, pdf_workers=None):
    """Process all PDFs in the input folder using multi-threading."""
    
    # Check if input folder exists
    if not os.path.exists(input_folder):
        print(f"Error: Input folder '{input_folder}' not found!")
        return
    
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Find all PDF files in input folder
    pdf_files = glob.glob(os.path.join(input_folder, "*.pdf"))
    
    if not pdf_files:
        print(f"No PDF files found in '{input_folder}' folder.")
        return
    
    filter_display = " AND ".join([f"'{s}'" for s in filter_strings])
    print(f"Found {len(pdf_files)} PDF files to process.")
    print(f"Filter strings: {filter_display} (case sensitive: {case_sensitive})")
    print(f"Input folder: '{input_folder}'")
    print(f"Output folder: '{output_folder}'")
    print(f"PDF workers: {pdf_workers or 'auto'}, Page workers per PDF: {max_workers or 'auto'}")
    print("-" * 50)
    
    # Prepare arguments for parallel PDF processing
    pdf_args = [(pdf_file, output_folder, filter_strings, case_sensitive, max_workers) 
                for pdf_file in pdf_files]
    
    # Process PDFs in parallel while maintaining order
    with ThreadPoolExecutor(max_workers=pdf_workers) as executor:
        # Use map to maintain order of processing
        results = list(executor.map(process_single_pdf, pdf_args))
    
    # Count total sections created
    total_sections = sum(results)
    
    print(f"\n{'='*50}")
    print(f"Processing complete! Created {total_sections} section PDFs from {len(pdf_files)} input files.")


def split_pdf_by_detections(input_folder, output_folder, filter_strings, case_sensitive=False):
    """
    Split PDFs in a folder into sections based on detection pages.
    This function can be called with parameters instead of using configuration variables.
    """
    # Validate configuration
    if not filter_strings:
        print("Error: filter_strings cannot be empty! Please add at least one filter string.")
        return
    
    # Remove empty strings from filter list
    filter_strings = [s.strip() for s in filter_strings if s.strip()]
    if not filter_strings:
        print("Error: All filter strings are empty! Please add valid filter strings.")
        return
    
    print("PDF Section Splitter (Multi-threaded)")
    print("=" * 50)
    
    # Process input folder
    process_input_folder(input_folder, output_folder, filter_strings, case_sensitive, PAGE_WORKERS, PDF_WORKERS)


def main():
    """Main function that uses the configuration variables."""
    
    # Validate configuration
    if not FILTER_STRINGS:
        print("Error: FILTER_STRINGS cannot be empty! Please add at least one filter string.")
        return
    
    # Remove empty strings from filter list
    filter_strings = [s.strip() for s in FILTER_STRINGS if s.strip()]
    if not filter_strings:
        print("Error: All filter strings are empty! Please add valid filter strings.")
        return
    
    print("PDF Section Splitter (Multi-threaded)")
    print("=" * 50)
    
    if SINGLE_FILE:
        # Process single file
        if not os.path.exists(SINGLE_FILE):
            print(f"Error: File '{SINGLE_FILE}' not found!")
            return
        
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        
        filter_display = " AND ".join([f"'{s}'" for s in filter_strings])
        print(f"Processing single file: {SINGLE_FILE}")
        print(f"Filter strings: {filter_display} (case sensitive: {CASE_SENSITIVE})")
        print(f"Page workers: {PAGE_WORKERS or 'auto'}")
        print("-" * 50)
        
        # Find detections and create sections
        detection_pages, total_pages = find_detection_pages(SINGLE_FILE, filter_strings, CASE_SENSITIVE, PAGE_WORKERS)
        
        if detection_pages:
            print(f"Found {len(detection_pages)} detections on pages: {[p+1 for p in detection_pages]}")
            created_count = create_pdf_sections(SINGLE_FILE, OUTPUT_FOLDER, detection_pages, total_pages)
            print(f"✓ Created {created_count} section PDFs")
        else:
            print("✗ No detections found")
    else:
        # Process folder
        process_input_folder(INPUT_FOLDER, OUTPUT_FOLDER, filter_strings, CASE_SENSITIVE, PAGE_WORKERS, PDF_WORKERS)


if __name__ == "__main__":
    main() 