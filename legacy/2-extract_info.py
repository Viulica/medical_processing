
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

# Thread-local storage for temporary files cleanup

thread_local = threading.local()


def extract_single_page_as_pdf(input_pdf_path, page_number):
    """Extract a single page from PDF and return as temporary PDF file."""
    try:
        reader = PdfReader(input_pdf_path)
        writer = PdfWriter()
        
        # Add the specific page (convert from 1-based to 0-based indexing)
        if 1 <= page_number <= len(reader.pages):
            writer.add_page(reader.pages[page_number - 1])
            
            # Create temporary file for the single page
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            writer.write(temp_file)
            temp_file.close()
            
            return temp_file.name
        else:
            print(f"  Warning: Page {page_number} is out of range")
            return None
            
    except Exception as e:
        print(f"  Error extracting page {page_number}: {str(e)}")
        return None


def extract_info_from_single_page(client, page_pdf_path, page_number, extraction_prompt, model="gemini-2.5-pro"):
    """Extract patient information from a single page PDF file."""
    try:
        with open(page_pdf_path, "rb") as pdf_file:
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

        # Collect the full response
        full_response = ""
        for chunk in client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=generate_content_config,
        ):
            if chunk.text is not None:
                full_response += chunk.text
        
        return full_response.strip()
    
    except Exception as e:
        print(f"  Error processing page {page_number}: {str(e)}")
        return None


def extract_info_from_single_page_with_order(client, page_pdf_path, page_number, extraction_prompt, model="gemini-2.5-pro", max_retries=5):
    """Extract patient information from a single page PDF file and return with page number for ordering."""
    
    for attempt in range(max_retries):
        try:
            with open(page_pdf_path, "rb") as pdf_file:
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
                print(f"      ✓ Successfully processed page {page_number} on attempt {attempt + 1}")
                return page_number, response_text
                
            except json.JSONDecodeError as e:
                print(f"      ⚠ JSON parsing failed for page {page_number} (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt == max_retries - 1:
                    print(f"      ✗ Final JSON parsing failure for page {page_number}")
                    print(f"      Raw response: {response_text[:200]}...")
                    return page_number, None
                # Continue to retry logic below
                
            except Exception as api_error:
                print(f"      ⚠ API call failed for page {page_number} (attempt {attempt + 1}/{max_retries}): {str(api_error)}")
                if attempt == max_retries - 1:
                    print(f"      ✗ Final API failure for page {page_number}")
                    return page_number, None
                # Continue to retry logic below
        
        except Exception as e:
            print(f"      ⚠ Unexpected error for page {page_number} (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt == max_retries - 1:
                print(f"      ✗ Final failure for page {page_number}")
                return page_number, None
        
        # Exponential backoff with jitter for retries
        if attempt < max_retries - 1:
            base_delay = 2 ** attempt  # 1, 2, 4, 8 seconds
            jitter = random.uniform(0.5, 1.5)  # Add randomness to prevent thundering herd
            delay = base_delay * jitter
            print(f"      ⏳ Retrying page {page_number} in {delay:.1f} seconds...")
            time.sleep(delay)
    
    return page_number, None


def process_single_page_task(args):
    """Task function for processing a single page in a thread."""
    client, pdf_file_path, page_num, extraction_prompt = args
    
    # Extract single page as temporary PDF
    temp_page_pdf = extract_single_page_as_pdf(pdf_file_path, page_num)
    if not temp_page_pdf:
        return page_num, None, temp_page_pdf
        
    # Extract info from this single page with retry logic
    page_number, response = extract_info_from_single_page_with_order(client, temp_page_pdf, page_num, extraction_prompt)
    
    return page_number, response, temp_page_pdf


def process_pdf_page_by_page(client, pdf_file_path, extraction_prompt, max_workers=5):
    """Process a single PDF file page by page using multi-threading and return all extracted data in order."""
    pdf_data = []
    temp_files = []  # Keep track of temporary files for cleanup
    
    try:
        # Get total number of pages
        reader = PdfReader(pdf_file_path)
        total_pages = len(reader.pages)
        print(f"  Total pages: {total_pages}")
        print(f"  Using {min(max_workers, total_pages)} threads for processing (with 5 retries per page)")
        
        # Prepare tasks for all pages
        tasks = []
        for page_num in range(1, total_pages + 1):
            tasks.append((client, pdf_file_path, page_num, extraction_prompt))
        
        # Process pages concurrently
        page_results = {}  # Dictionary to store results by page number
        failed_pages = []  # Track pages that failed completely
        
        with ThreadPoolExecutor(max_workers=min(max_workers, total_pages)) as executor:
            # Submit all tasks
            future_to_page = {executor.submit(process_single_page_task, task): task[2] for task in tasks}
            
            # Collect results as they complete
            for future in as_completed(future_to_page):
                page_num = future_to_page[future]
                try:
                    page_number, response, temp_page_pdf = future.result()
                    
                    if temp_page_pdf:
                        temp_files.append(temp_page_pdf)
                    
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
                            
                            # Parse the JSON response (should work since we validated it in retry logic)
                            extracted_record = json.loads(cleaned_response)
                            
                            # Store result with page number for later sorting
                            page_results[page_number] = extracted_record
                            
                        except json.JSONDecodeError as e:
                            # This shouldn't happen since we validate in the retry logic, but just in case
                            print(f"      ✗ Final JSON parsing error for page {page_number}: {str(e)}")
                            failed_pages.append(page_number)
                    else:
                        print(f"      ✗ All retries failed for page {page_number}")
                        failed_pages.append(page_number)
                        
                except Exception as e:
                    print(f"      ✗ Exception processing page {page_num}: {str(e)}")
                    failed_pages.append(page_num)
        
        # Sort results by page number to maintain order
        for page_num in sorted(page_results.keys()):
            pdf_data.append(page_results[page_num])
        
        success_count = len(pdf_data)
        fail_count = len(failed_pages)
        
        if fail_count > 0:
            print(f"  ⚠ Successfully processed {success_count} pages, {fail_count} pages failed after retries")
            print(f"    Failed pages: {sorted(failed_pages)}")
        else:
            print(f"  ✓ Successfully processed all {success_count} pages in correct order")
                
    except Exception as e:
        print(f"  Error processing PDF: {str(e)}")
    
    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            try:
                os.unlink(temp_file)
            except:
                pass
    
    return pdf_data


def process_all_pdfs(excel_file_path="WPA for testing FINAL.xlsx", max_workers=5):
    """Process all PDFs in the output folder using specified Excel field definitions with multi-threading."""
    
    # Check if Excel file exists
    if not os.path.exists(excel_file_path):
        print(f"Error: Excel file '{excel_file_path}' not found!")
        return
    
    print(f"Using field definitions from: {excel_file_path}")
    print(f"Max concurrent threads per PDF: {max_workers}")
    
    # Generate extraction prompt from Excel file
    extraction_prompt = generate_extraction_prompt(excel_file_path)
    fieldnames = get_fieldnames(excel_file_path)
    
    # Save the prompt to a text file for easy copying
    with open("extraction_prompt.txt", "w", encoding="utf-8") as prompt_file:
        prompt_file.write(extraction_prompt)
    print(f"✓ Saved extraction prompt to 'extraction_prompt.txt'")
    
    # Remove system fields from CSV output
    fieldnames = [field for field in fieldnames if field not in ['source_file', 'page_number']]
    
    # Initialize Google AI client
    client = genai.Client(
        api_key="AIzaSyCrskRv2ajNhc-KqDVv0V8KFl5Bdf5rr7w",
    )
    
    # Find all PDF files in the output folder
    output_folder = "output"
    pdf_files = glob.glob(os.path.join(output_folder, "*.pdf"))
    
    if not pdf_files:
        print("No PDF files found in the output folder.")
        return
    
    print(f"Found {len(pdf_files)} PDF files to process.")
    
    # Process each PDF file separately
    for pdf_file in pdf_files:
        print(f"\nProcessing: {os.path.basename(pdf_file)}")
        
        # Extract data from all pages of this PDF (multi-threaded)
        pdf_extracted_data = process_pdf_page_by_page(client, pdf_file, extraction_prompt, max_workers)
        
        if pdf_extracted_data:
            # Create CSV filename based on original PDF name
            base_name = os.path.splitext(os.path.basename(pdf_file))[0]
            # Filter extracted data to only include expected fields
            filtered_data = []
            for record in pdf_extracted_data:
                filtered_record = {}
                for field in fieldnames:
                    value = record.get(field, None)
                    # Ensure ID fields and numeric-looking strings stay as strings
                    if value is not None and isinstance(value, (str, int, float)):
                        value = str(value)
                        
                    filtered_record[field] = value
                filtered_data.append(filtered_record)
            
            extracted_folder = "extracted"
            os.makedirs(extracted_folder, exist_ok=True)
            
            # Save as both CSV and Excel formats
            csv_filename = f"{base_name}_extracted_data.csv"
            excel_filename = f"{base_name}_extracted_data.xlsx"
            
            # CSV output (clean data for medical billing apps)
            extracted_csv_filename = os.path.join(extracted_folder, csv_filename)
            with open(extracted_csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(filtered_data)
            
            # Excel output (preserves data types, no scientific notation)
            extracted_excel_filename = os.path.join(extracted_folder, excel_filename)
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
            
            df.to_excel(extracted_excel_filename, index=False, engine='openpyxl')
            
            print(f"  ✓ Created {csv_filename} with {len(pdf_extracted_data)} records (clean CSV for imports)")
            print(f"  ✓ Created {excel_filename} with {len(pdf_extracted_data)} records (Excel format, no scientific notation)")
        else:
            print(f"  ✗ No data extracted from {os.path.basename(pdf_file)}")
    
    print(f"\n✓ Processing complete!")


if __name__ == "__main__":
    # Allow specifying Excel file and max workers as command line arguments
    max_workers = 5  # Default thread pool size
    if len(sys.argv) > 1:
        excel_file = sys.argv[1]
        if len(sys.argv) > 2:
            try:
                max_workers = int(sys.argv[2])
            except ValueError:
                print("Warning: Invalid max_workers value, using default of 5")
    else:
        excel_file = "WPA for testing FINAL.xlsx"
    
    process_all_pdfs(excel_file, max_workers)
