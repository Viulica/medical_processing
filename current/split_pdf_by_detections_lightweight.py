#!/usr/bin/env python3
"""
Lightweight PDF splitting script using pdfplumber instead of PyMuPDF.
This version doesn't require compilation and should work better in Streamlit.
"""

import os
import sys
import argparse
import pdfplumber
from PyPDF2 import PdfReader, PdfWriter
from pathlib import Path
import re

def extract_text_from_pdf_page(pdf_path, page_number):
    """
    Extract text from a PDF page using pdfplumber.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_number < len(pdf.pages):
                page = pdf.pages[page_number]
                text = page.extract_text()
                return text if text else ""
            else:
                return ""
    except Exception as e:
        print(f"Error extracting text from page {page_number}: {str(e)}")
        return ""

def check_page_contains_all_strings(pdf_path, page_number, filter_strings, case_sensitive=False):
    """
    Check if a PDF page contains ALL the specified filter strings (AND logic).
    Uses pdfplumber for text extraction instead of OCR.
    """
    try:
        # Extract text from the page
        page_text = extract_text_from_pdf_page(pdf_path, page_number)
        
        if not page_text:
            return False
        
        # Check if ALL filter strings are present (AND logic)
        if not case_sensitive:
            page_text_lower = page_text.lower()
            return all(filter_string.lower() in page_text_lower for filter_string in filter_strings)
        else:
            return all(filter_string in page_text for filter_string in filter_strings)
            
    except Exception as e:
        print(f"Error checking page {page_number}: {str(e)}")
        return False

def find_detection_pages(input_pdf_path, filter_strings, case_sensitive=False):
    """
    Find all pages that match the detection criteria.
    """
    try:
        reader = PdfReader(input_pdf_path)
        total_pages = len(reader.pages)
        
        filter_display = " AND ".join([f"'{s}'" for s in filter_strings])
        print(f"  Scanning {total_pages} pages for detections...")
        print(f"  Looking for pages containing: {filter_display}")
        
        detection_pages = []
        
        for page_num in range(total_pages):
            if check_page_contains_all_strings(input_pdf_path, page_num, filter_strings, case_sensitive):
                detection_pages.append(page_num)
                print(f"    Found detection on page {page_num + 1}")
        
        print(f"  Found {len(detection_pages)} detection pages")
        return detection_pages
        
    except Exception as e:
        print(f"Error finding detection pages: {str(e)}")
        return []

def split_pdf_by_detections(input_folder, output_folder, filter_strings, case_sensitive=False):
    """
    Split PDFs in a folder into sections based on detection pages.
    """
    try:
        # Create output directory if it doesn't exist
        os.makedirs(output_folder, exist_ok=True)
        
        # Find all PDF files in input folder
        input_path = Path(input_folder)
        pdf_files = list(input_path.glob('*.pdf'))
        
        if not pdf_files:
            print(f"No PDF files found in {input_folder}")
            return
        
        print(f"Found {len(pdf_files)} PDF files to process")
        
        for pdf_file in pdf_files:
            print(f"\nProcessing: {pdf_file.name}")
            try:
                # Find detection pages for this PDF
                detection_pages = find_detection_pages(str(pdf_file), filter_strings, case_sensitive)
                
                if not detection_pages:
                    print("No detection pages found. Creating single output file.")
                    # If no detections found, create one file with all pages
                    reader = PdfReader(str(pdf_file))
                    writer = PdfWriter()
                    
                    for page in reader.pages:
                        writer.add_page(page)
                    
                    output_path = os.path.join(output_folder, f"{pdf_file.stem}_all_pages.pdf")
                    with open(output_path, 'wb') as output_file:
                        writer.write(output_file)
                    
                    print(f"Created single output file: {output_path}")
                    continue
                
                # Split PDF into sections
                reader = PdfReader(str(pdf_file))
                total_pages = len(reader.pages)
                
                # Add start and end boundaries
                all_boundaries = [0] + detection_pages + [total_pages]
                
                # Create sections
                for i in range(len(all_boundaries) - 1):
                    start_page = all_boundaries[i]
                    end_page = all_boundaries[i + 1]
                    
                    if start_page == end_page:
                        continue
                    
                    writer = PdfWriter()
                    
                    for page_num in range(start_page, end_page):
                        if page_num < total_pages:
                            writer.add_page(reader.pages[page_num])
                    
                    # Generate output filename
                    section_num = i + 1
                    pages_range = f"pages_{start_page + 1}-{end_page}"
                    output_filename = f"{pdf_file.stem}_section_{section_num:02d}_{pages_range}.pdf"
                    output_path = os.path.join(output_folder, output_filename)
                    
                    with open(output_path, 'wb') as output_file:
                        writer.write(output_file)
                    
                    print(f"Created section {section_num}: {output_filename}")
                
                print(f"✅ Successfully processed {pdf_file.name}")
                
            except Exception as e:
                print(f"❌ Error processing {pdf_file.name}: {str(e)}")
                continue
    
    except Exception as e:
        print(f"Error splitting PDFs: {str(e)}")
        raise

def main():
    parser = argparse.ArgumentParser(description='Split PDF by detection strings')
    parser.add_argument('input_folder', help='Input folder containing PDF files')
    parser.add_argument('output_folder', help='Output folder for split PDFs')
    parser.add_argument('--filter-strings', nargs='+', required=True, help='Filter strings to detect')
    parser.add_argument('--case-sensitive', action='store_true', help='Case sensitive matching')
    
    args = parser.parse_args()
    
    # Process all PDF files in input folder
    input_path = Path(args.input_folder)
    output_path = Path(args.output_folder)
    
    if not input_path.exists():
        print(f"Error: Input folder {input_path} does not exist")
        sys.exit(1)
    
    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Find all PDF files
    pdf_files = list(input_path.glob('*.pdf'))
    
    if not pdf_files:
        print(f"No PDF files found in {input_path}")
        sys.exit(1)
    
    print(f"Found {len(pdf_files)} PDF files to process")
    
    for pdf_file in pdf_files:
        print(f"\nProcessing: {pdf_file.name}")
        try:
            split_pdf_by_detections(
                str(pdf_file),
                str(output_path),
                args.filter_strings,
                args.case_sensitive
            )
            print(f"✅ Successfully processed {pdf_file.name}")
        except Exception as e:
            print(f"❌ Error processing {pdf_file.name}: {str(e)}")
    
    print(f"\nProcessing complete. Output files saved to: {output_path}")

if __name__ == "__main__":
    main() 