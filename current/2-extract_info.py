import os
import json
import csv
import glob
import tempfile
import sys
import time
import random
import pandas as pd
import google.genai as genai
from google.genai import types
from PyPDF2 import PdfReader, PdfWriter
from field_definitions import get_fieldnames, generate_extraction_prompt
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import re

# Thread-local storage for temporary files cleanup
thread_local = threading.local()


def format_phone_number(phone_str):
    """Format phone number to add space after area code: (712)301-6622 -> (712) 301-6622"""
    if not phone_str or not isinstance(phone_str, str):
        return phone_str
    
    # Remove any existing spaces first to standardize
    phone_str = phone_str.strip().replace(' ', '')
    
    # Pattern to match phone numbers like (712)301-6622 or (712)3016622
    pattern = r'^\((\d{3})\)(\d{3})[-]?(\d{4})$'
    match = re.match(pattern, phone_str)
    
    if match:
        area_code, prefix, line = match.groups()
        return f"({area_code}) {prefix}-{line}"
    
    # If it doesn't match the expected pattern, return as is
    return phone_str


def clean_field_value(value, field_name=None):
    """Clean field values by removing unwanted characters like ? at the beginning"""
    if not value or not isinstance(value, str):
        return value
    
    # Remove common problematic characters at the beginning
    cleaned = value.strip()
    
    # Remove question marks at the beginning (common encoding issue)
    while cleaned.startswith('?'):
        cleaned = cleaned[1:].strip()
    
    # Remove other common invisible/problematic characters
    # Remove zero-width space, non-breaking space, BOM, etc.
    cleaned = cleaned.lstrip('\ufeff\u200b\u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000')
    
    # Remove any remaining leading/trailing whitespace
    cleaned = cleaned.strip()
    
    # Remove any question marks that might appear in the middle due to encoding issues
    # This is more aggressive cleaning for problematic characters
    cleaned = cleaned.replace('?', '')
    
    # CRITICAL FIX: Remove newlines that break CSV structure in Excel
    # Replace newlines with semicolons for addresses to maintain readability
    cleaned = cleaned.replace('\n', '; ').replace('\r', '; ')
    
    # Remove multiple consecutive semicolons and spaces
    while '; ; ' in cleaned:
        cleaned = cleaned.replace('; ; ', '; ')
    
    # Remove trailing semicolons
    cleaned = cleaned.rstrip('; ')
    
    # SPECIAL CLEANING FOR SUBSCRIPTION ID FIELDS
    # Remove special characters from subscription ID fields
    if field_name and any(id_type in field_name.lower() for id_type in ['subsc id', 'subscription id']):
        # Remove common special characters that shouldn't be in IDs
        import re
        # Keep only alphanumeric characters and common ID separators
        cleaned = re.sub(r'[^a-zA-Z0-9\-_\.]', '', cleaned)
    
    return cleaned


def extract_first_n_pages_as_pdf(input_pdf_path, n_pages=2):
    """Extract the first n pages from PDF and return as temporary PDF file."""
    try:
        reader = PdfReader(input_pdf_path)
        writer = PdfWriter()
        
        total_pages = len(reader.pages)
        pages_to_extract = min(n_pages, total_pages)
        
        print(f"    📄 Extracting first {pages_to_extract} pages from {total_pages} total pages")
        
        # Add the first n pages
        for page_idx in range(pages_to_extract):
            writer.add_page(reader.pages[page_idx])
        
        # Create temporary file for the combined pages
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.PDF')
        writer.write(temp_file)
        temp_file.close()
        
        return temp_file.name
            
    except Exception as e:
        print(f"    ❌ Error extracting first {n_pages} pages: {str(e)}")
        return None


def extract_info_from_patient_pdf(client, patient_pdf_path, pdf_filename, extraction_prompt, model="gemini-2.5-pro", max_retries=5):
    """Extract patient information from a multi-page patient PDF file."""
    
    for attempt in range(max_retries):
        try:
            with open(patient_pdf_path, "rb") as pdf_file:
                pdf_data = pdf_file.read()
            
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(
                            mime_type="application/pdf",
                            data=pdf_data,
                        ),
                        types.Part.from_text(text=extraction_prompt)],
                )
            ]
            
            generate_content_config = types.GenerateContentConfig(
                response_mime_type="text/plain",
            )

            # Collect the full response with retry on API failures
            full_response = ""
            try:
                for chunk in client.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=generate_content_config,
                ):
                    if chunk.text is not None:
                        full_response += chunk.text
                
                response_text = full_response.strip()
                
                # Validate that we got a meaningful response
                if not response_text or len(response_text) < 10:
                    raise ValueError(f"Response too short or empty: {response_text}")
                
                # Try to parse JSON to validate response format
                cleaned_response = response_text
                if cleaned_response.startswith('```json'):
                    cleaned_response = cleaned_response[7:]  # Remove ```json
                if cleaned_response.startswith('```'):
                    cleaned_response = cleaned_response[3:]   # Remove ```
                if cleaned_response.endswith('```'):
                    cleaned_response = cleaned_response[:-3]  # Remove trailing ```
                cleaned_response = cleaned_response.strip()
                
                # Parse JSON to validate format (this will raise JSONDecodeError if invalid)
                json.loads(cleaned_response)
                
                # If we get here, everything worked
                print(f"    ✅ Successfully processed {pdf_filename} on attempt {attempt + 1}")
                return response_text
                
            except json.JSONDecodeError as e:
                print(f"    ⚠️  JSON parsing failed for {pdf_filename} (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt == max_retries - 1:
                    print(f"    ❌ Final JSON parsing failure for {pdf_filename}")
                    print(f"    Raw response: {response_text[:200]}...")
                    return None
                # Continue to retry logic below
                
            except Exception as api_error:
                print(f"    ⚠️  API call failed for {pdf_filename} (attempt {attempt + 1}/{max_retries}): {str(api_error)}")
                if attempt == max_retries - 1:
                    print(f"    ❌ Final API failure for {pdf_filename}")
                    return None
                # Continue to retry logic below
        
        except Exception as e:
            print(f"    ⚠️  Unexpected error for {pdf_filename} (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt == max_retries - 1:
                print(f"    ❌ Final failure for {pdf_filename}")
                return None
        
        # Exponential backoff with jitter for retries
        if attempt < max_retries - 1:
            base_delay = 2 ** attempt  # 1, 2, 4, 8 seconds
            jitter = random.uniform(0.5, 1.5)  # Add randomness to prevent thundering herd
            delay = base_delay * jitter
            print(f"    ⏳ Retrying {pdf_filename} in {delay:.1f} seconds...")
            time.sleep(delay)
    
    return None


def process_single_patient_pdf_task(args):
    """Task function for processing a single patient PDF in a thread."""
    client, pdf_file_path, extraction_prompt, n_pages = args
    
    pdf_filename = os.path.basename(pdf_file_path)
    
    # Extract first n pages as temporary PDF
    temp_patient_pdf = extract_first_n_pages_as_pdf(pdf_file_path, n_pages)
    if not temp_patient_pdf:
        return pdf_filename, None, temp_patient_pdf
        
    # Extract info from this patient's combined pages
    response = extract_info_from_patient_pdf(client, temp_patient_pdf, pdf_filename, extraction_prompt)
    
    return pdf_filename, response, temp_patient_pdf


def process_all_patient_pdfs(input_folder="input", excel_file_path="WPA for testing FINAL.xlsx", n_pages=2, max_workers=5):
    """Process all patient PDFs in the input folder, combining first n pages per patient into one CSV."""
    
    # Check if Excel file exists
    if not os.path.exists(excel_file_path):
        print(f"❌ Error: Excel file '{excel_file_path}' not found!")
        return
    
    print(f"📋 Using field definitions from: {excel_file_path}")
    print(f"📄 Processing first {n_pages} pages per patient PDF")
    print(f"🧵 Max concurrent threads: {max_workers}")
    
    # Generate extraction prompt from Excel file
    extraction_prompt = generate_extraction_prompt(excel_file_path)
    fieldnames = get_fieldnames(excel_file_path)
    
    # Remove system fields from CSV output
    fieldnames = [field for field in fieldnames if field not in ['source_file', 'page_number']]
    
    # Initialize Google AI client
    client = genai.Client(
        api_key="AIzaSyCrskRv2ajNhc-KqDVv0V8KFl5Bdf5rr7w",
    )
    
    # Find all PDF files in the input folder (both uppercase and lowercase extensions)
    pdf_files = glob.glob(os.path.join(input_folder, "*.pdf")) + glob.glob(os.path.join(input_folder, "*.PDF"))
    
    if not pdf_files:
        print(f"❌ No PDF files found in the '{input_folder}' folder.")
        return
    
    print(f"📁 Found {len(pdf_files)} patient PDF files to process.")
    
    # Process all PDFs concurrently
    all_extracted_data = []
    temp_files = []  # Keep track of temporary files for cleanup
    failed_pdfs = []  # Track PDFs that failed completely
    
    try:
        # Prepare tasks for all PDFs
        tasks = []
        for pdf_file in pdf_files:
            tasks.append((client, pdf_file, extraction_prompt, n_pages))
        
        print(f"\n🚀 Starting concurrent processing of {len(tasks)} patient PDFs...")
        
        with ThreadPoolExecutor(max_workers=min(max_workers, len(pdf_files))) as executor:
            # Submit all tasks
            future_to_pdf = {executor.submit(process_single_patient_pdf_task, task): task[1] for task in tasks}
            
            # Collect results as they complete
            for future in as_completed(future_to_pdf):
                pdf_file_path = future_to_pdf[future]
                pdf_filename = os.path.basename(pdf_file_path)
                
                try:
                    filename, response, temp_patient_pdf = future.result()
                    
                    if temp_patient_pdf:
                        temp_files.append(temp_patient_pdf)
                    
                    if response:
                        try:
                            # Clean the response by removing markdown code block formatting
                            cleaned_response = response.strip()
                            if cleaned_response.startswith('```json'):
                                cleaned_response = cleaned_response[7:]  # Remove ```json
                            if cleaned_response.startswith('```'):
                                cleaned_response = cleaned_response[3:]   # Remove ```
                            if cleaned_response.endswith('```'):
                                cleaned_response = cleaned_response[:-3]  # Remove trailing ```
                            cleaned_response = cleaned_response.strip()
                            
                            # Parse the JSON response
                            extracted_record = json.loads(cleaned_response)
                            
                            # Clean and format all field values
                            for field_name, value in extracted_record.items():
                                if value:
                                    # First clean the value (removes ?, invisible chars, etc.)
                                    cleaned_value = clean_field_value(value, field_name)
                                    
                                    # Then apply specific formatting for phone numbers
                                    if 'phone' in field_name.lower():
                                        cleaned_value = format_phone_number(cleaned_value)
                                    
                                    extracted_record[field_name] = cleaned_value
                            
                            # Add source file info for reference
                            extracted_record['source_file'] = pdf_filename
                            
                            all_extracted_data.append(extracted_record)
                            print(f"  ✅ Successfully added data for {pdf_filename}")
                            
                        except json.JSONDecodeError as e:
                            print(f"  ❌ JSON parsing error for {pdf_filename}: {str(e)}")
                            failed_pdfs.append(pdf_filename)
                    else:
                        print(f"  ❌ All retries failed for {pdf_filename}")
                        failed_pdfs.append(pdf_filename)
                        
                except Exception as e:
                    print(f"  ❌ Exception processing {pdf_filename}: {str(e)}")
                    failed_pdfs.append(pdf_filename)
        
        # Summary of processing
        success_count = len(all_extracted_data)
        fail_count = len(failed_pdfs)
        
        if fail_count > 0:
            print(f"\n⚠️  Successfully processed {success_count} PDFs, {fail_count} PDFs failed after retries")
            print(f"   Failed PDFs: {sorted(failed_pdfs)}")
        else:
            print(f"\n🎉 Successfully processed all {success_count} patient PDFs")
        
        # Create the combined CSV file
        if all_extracted_data:
            # Filter extracted data to only include expected fields (exclude source_file from final output)
            filtered_data = []
            for record in all_extracted_data:
                filtered_record = {}
                for field in fieldnames:
                    value = record.get(field, None)
                    # Ensure ID fields and numeric-looking strings stay as strings
                    if value is not None and isinstance(value, (str, int, float)):
                        value = str(value)
                        # Clean the value one more time (removes ?, invisible chars, etc.)
                        value = clean_field_value(value, field)
                        
                    filtered_record[field] = value
                filtered_data.append(filtered_record)
            
            # Save to both CSV and Excel formats
            extracted_folder = "extracted"
            os.makedirs(extracted_folder, exist_ok=True)
            
            # Create combined filenames with timestamp
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            combined_csv_filename = f"combined_patient_data_{timestamp}.csv"
            combined_excel_filename = f"combined_patient_data_{timestamp}.xlsx"
            extracted_csv_path = os.path.join(extracted_folder, combined_csv_filename)
            extracted_excel_path = os.path.join(extracted_folder, combined_excel_filename)
            
            # CSV output (clean data for medical billing apps)
            with open(extracted_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(filtered_data)
            
            # Excel output (preserves data types, no scientific notation)
            df = pd.DataFrame(filtered_data)
            
            # Replace None values with empty strings for cleaner Excel display
            df = df.fillna('')
            
            # Replace 'None' strings with empty strings (in case any slipped through)
            df = df.replace('None', '')
            
            # Explicitly set ID columns as text to prevent scientific notation
            id_columns = ['Primary Subsc ID', 'Secondary Subsc ID', 'MRN', 'CSN']
            for col in id_columns:
                if col in df.columns:
                    # Only convert non-empty values to string to avoid 'nan' text
                    df[col] = df[col].apply(lambda x: str(x) if x != '' else '')
            
            df.to_excel(extracted_excel_path, index=False, engine='openpyxl')
            
            print(f"📊 Created {combined_csv_filename} with {len(filtered_data)} patient records (clean CSV for imports)")
            print(f"   CSV saved to: {extracted_csv_path}")
            print(f"📊 Created {combined_excel_filename} with {len(filtered_data)} patient records (Excel format, no scientific notation)")
            print(f"   Excel saved to: {extracted_excel_path}")
        else:
            print(f"❌ No data extracted from any PDF files")
                
    except Exception as e:
        print(f"❌ Error during processing: {str(e)}")
    
    finally:
        # Clean up temporary files
        print(f"🧹 Cleaning up {len(temp_files)} temporary files...")
        for temp_file in temp_files:
            try:
                os.unlink(temp_file)
            except:
                pass
    
    print(f"\n✅ Processing complete!")


if __name__ == "__main__":
    # Allow specifying input folder, Excel file, number of pages, and max workers as command line arguments
    input_folder = "input"  # Default input folder
    excel_file = "WPA for testing FINAL.xlsx"  # Default Excel file
    n_pages = 2  # Default number of pages to extract per patient
    max_workers = 5  # Default thread pool size
    
    if len(sys.argv) > 1:
        input_folder = sys.argv[1]
    if len(sys.argv) > 2:
        excel_file = sys.argv[2]
    if len(sys.argv) > 3:
        try:
            n_pages = int(sys.argv[3])
        except ValueError:
            print("⚠️  Warning: Invalid n_pages value, using default of 2")
    if len(sys.argv) > 4:
        try:
            max_workers = int(sys.argv[4])
        except ValueError:
            print("⚠️  Warning: Invalid max_workers value, using default of 5")
    
    print(f"🔧 Configuration:")
    print(f"   Input folder: {input_folder}")
    print(f"   Excel file: {excel_file}")
    print(f"   Pages per patient: {n_pages}")
    print(f"   Max workers: {max_workers}")
    print()
    
    process_all_patient_pdfs(input_folder, excel_file, n_pages, max_workers) 