# ============================================================================
# CONFIGURATION - Edit these variables to customize the filtering
# ============================================================================

# Filter strings - ALL of these must be present on a page to keep it (AND logic)
WPA_FILTER_STRINGS = [
    "Anesthesia Billing",
    "Address 1",
    "Address 2",
    "Gender"
    # "another string",  # Add more strings as needed
]

STA_DGSS_FILTER_STRINGS = [
    "Patient Demographics Form",
]

STA_GLS_FILTER_STRINGS = [
    "Patient Information",
]


STA_GL_FILTER_STRINGS = [
    "PATIENT INFORMATION",
    "STREET ADRESS"
]


FILTER_STRINGS = WPA_FILTER_STRINGS

# Folder settings
INPUT_FOLDER = "input"          # Folder containing PDF files to process
OUTPUT_FOLDER = "output"        # Folder where filtered PDFs will be saved

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


def filter_pdf_pages(input_pdf_path, output_pdf_path, filter_strings, case_sensitive=False, max_workers=None):
    """Filter PDF pages based on OCR text content using multi-threading."""
    try:
        reader = PdfReader(input_pdf_path)
        writer = PdfWriter()
        total_pages = len(reader.pages)
        pages_kept = 0
        
        filter_display = " AND ".join([f"'{s}'" for s in filter_strings])
        thread_safe_print(f"  Processing {total_pages} pages with {max_workers or 'auto'} threads...")
        thread_safe_print(f"  Looking for pages containing: {filter_display}")
        
        # Prepare arguments for parallel processing
        page_args = [(input_pdf_path, page_num, filter_strings, case_sensitive) 
                     for page_num in range(total_pages)]
        
        # Process pages in parallel while maintaining order
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Use map to maintain order of results
            results = list(executor.map(check_page_contains_text_wrapper, page_args))
        
        # Process results in order and build the filtered PDF
        for page_num, contains_all_strings in results:
            thread_safe_print(f"    Page {page_num + 1}/{total_pages}...", end=" ")
            
            if contains_all_strings:
                # Keep this page
                writer.add_page(reader.pages[page_num])
                pages_kept += 1
                thread_safe_print("✓ KEPT")
            else:
                thread_safe_print("✗ FILTERED OUT")
        
        # Save the filtered PDF
        if pages_kept > 0:
            with open(output_pdf_path, 'wb') as output_file:
                writer.write(output_file)
            thread_safe_print(f"  ✓ Saved {pages_kept}/{total_pages} pages to {output_pdf_path}")
            return True
        else:
            thread_safe_print(f"  ✗ No pages contained all filter strings")
            return False
            
    except Exception as e:
        thread_safe_print(f"  Error processing PDF: {str(e)}")
        return False


def process_single_pdf(args):
    """Process a single PDF file - wrapper for use with ThreadPoolExecutor.map()"""
    pdf_file, output_folder, filter_strings, case_sensitive, max_workers = args
    
    thread_safe_print(f"\nProcessing: {os.path.basename(pdf_file)}")
    
    # Create output filename
    base_name = os.path.splitext(os.path.basename(pdf_file))[0]
    output_filename = f"{base_name}_filtered.pdf"
    output_path = os.path.join(output_folder, output_filename)
    
    # Filter the PDF
    success = filter_pdf_pages(pdf_file, output_path, filter_strings, case_sensitive, max_workers)
    return success


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
    
    # Count successful processes
    processed_count = sum(results)
    
    print(f"\n{'='*50}")
    print(f"Processing complete! {processed_count}/{len(pdf_files)} files had matching pages.")


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
    
    print("PDF Multi-String Filter (Multi-threaded)")
    print("=" * 50)
    
    if SINGLE_FILE:
        # Process single file
        if not os.path.exists(SINGLE_FILE):
            print(f"Error: File '{SINGLE_FILE}' not found!")
            return
        
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(SINGLE_FILE))[0]
        output_path = os.path.join(OUTPUT_FOLDER, f"{base_name}_filtered.pdf")
        
        filter_display = " AND ".join([f"'{s}'" for s in filter_strings])
        print(f"Processing single file: {SINGLE_FILE}")
        print(f"Filter strings: {filter_display} (case sensitive: {CASE_SENSITIVE})")
        print(f"Page workers: {PAGE_WORKERS or 'auto'}")
        print("-" * 50)
        
        filter_pdf_pages(SINGLE_FILE, output_path, filter_strings, CASE_SENSITIVE, PAGE_WORKERS)
    else:
        # Process folder
        process_input_folder(INPUT_FOLDER, OUTPUT_FOLDER, filter_strings, CASE_SENSITIVE, PAGE_WORKERS, PDF_WORKERS)


if __name__ == "__main__":
    main() 