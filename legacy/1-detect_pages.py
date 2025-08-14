# To run this code you need to install the following dependencies:
# pip install google-genai PyPDF2

import base64
import os
import json
import re
import google.genai as genai
from google.genai import types
from PyPDF2 import PdfReader, PdfWriter

ANA_GCME_FIELDS = [
    "PATIENT NAME"
    "ADMIT DATE",
    "MEDICAL RECORD NO.",
    "BIRTHDATE",
    "AGE",
    "SEX",
    "Marital status (or MS for short)",
]


ANA_GCME_SPECIAL_HINT = ""


WPA_FIELDS = [
    "Patient Name", 
    "Address 1",
    "Address 2",
    "City, State, Zip",
    "Phone",
    "Gender",
    "MRN"
]

WPA_SPECIAL_HINT = """

BTW: IF IN THE TOP LEFT CORNET OF THE PAGE IT SAYS 'page 1 of 1' then extract the page (this is a SURE way of identifying a page that has to be extracted)

ONLY RETURN pages where it says "page 1 of 1" in the top left corner of the page
"""


IAC_FIELDS = [
    "Patient Name",
    "MRN",
    "Age",
    "Sex",
    "Date of Birth"
]

IAC_SPECIAL_HINT = """

BTW: if the page has a header with the words either "Final Report" or "Patient Information" or "Anesthesia billing summary", then this mage MUST be extracted, this is the basic info paage. no other pages should be extractedp"

"""

def detect_pages_with_gemini(pdf_base64, client):
    """Use Gemini API to detect relevant pages in a PDF"""
    model = "gemini-2.5-pro"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_bytes(
                    mime_type="application/pdf",
                    data=base64.b64decode(pdf_base64),
                ),
                types.Part.from_text(text="""
                                     
list out the page indexes where there is the basic info about the patient (for each full patient record there is always only one page where we find the basic information)
                                     
look for these field names and their values (roughly):
                              
{IAC_FIELDS}

{IAC_SPECIAL_HINT}
                                     
list out the page numbers in json format, that is your entire answer nothing else

i want the PAGE INDEXES

so i can cut out of the original pdf
                                    

page indexes start at 1!
                                     
"""),
            ],
        ),
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text="""Now analyze this PDF and return only the JSON array of page indexes."""),
            ],
        ),
    ]
    
    generate_content_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_budget=-1,
        ),
        response_mime_type="text/plain",
    )

    response_text = ""
    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    ):
        response_text += chunk.text
    
    return response_text


def extract_page_indexes(response_text):
    """Extract page indexes from Gemini API response"""
    # Try to find JSON array in the response
    json_match = re.search(r'\[[\d,\s]+\]', response_text)
    if json_match:
        try:
            page_indexes = json.loads(json_match.group())
            return page_indexes
        except json.JSONDecodeError:
            pass
    
    # If no valid JSON found, try to extract numbers
    numbers = re.findall(r'\b\d+\b', response_text)
    if numbers:
        return [int(num) for num in numbers]
    
    return []


def extract_pages_from_pdf(input_pdf_path, output_pdf_path, page_indexes):
    """Extract specific pages from PDF and save to new PDF"""
    reader = PdfReader(input_pdf_path)
    writer = PdfWriter()
    
    total_pages = len(reader.pages)
    print(f"  Total pages in PDF: {total_pages}")
    print(f"  Pages to extract: {page_indexes}")
    
    # Extract specified pages (convert from 1-based to 0-based indexing)
    extracted_count = 0
    for page_num in page_indexes:
        if 1 <= page_num <= total_pages:
            writer.add_page(reader.pages[page_num - 1])  # Convert to 0-based
            extracted_count += 1
        else:
            print(f"  Warning: Page {page_num} is out of range (1-{total_pages})")
    
    # Save the extracted pages
    if extracted_count > 0:
        with open(output_pdf_path, 'wb') as output_file:
            writer.write(output_file)
        print(f"  Extracted {extracted_count} pages to: {output_pdf_path}")
    else:
        print(f"  No valid pages to extract for this PDF")
    
    return extracted_count


def process_all_pdfs():
    """Main function to process all PDFs in input folder"""
    input_folder = "input"
    output_folder = "output"
    
    # Create output folder if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"Created output folder: {output_folder}")
    
    # Get all PDF files in input folder
    pdf_files = [f for f in os.listdir(input_folder) if f.endswith('.pdf')]
    
    if not pdf_files:
        print("No PDF files found in the input folder.")
        return
    
    print(f"Found {len(pdf_files)} PDF file(s) to process")
    
    # Initialize Gemini client
    client = genai.Client(
        api_key="AIzaSyCrskRv2ajNhc-KqDVv0V8KFl5Bdf5rr7w",
    )
    
    # Process each PDF
    for pdf_file in pdf_files:
        print(f"\n--- Processing: {pdf_file} ---")
        
        input_pdf_path = os.path.join(input_folder, pdf_file)
        output_pdf_path = os.path.join(output_folder, f"{pdf_file}")
        
        try:
            # Read and encode PDF file
            with open(input_pdf_path, 'rb') as file:
                pdf_data = file.read()
                pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')
            
            # Detect pages using Gemini API
            print("  Detecting relevant pages with Gemini API...")
            response_text = detect_pages_with_gemini(pdf_base64, client)
            
            # Extract page indexes from response
            page_indexes = extract_page_indexes(response_text)
            
            if page_indexes:
                print(f"  Detected page indexes: {page_indexes}")
                
                # Extract pages and save to new PDF
                extracted_count = extract_pages_from_pdf(input_pdf_path, output_pdf_path, page_indexes)
                
                if extracted_count == 0:
                    print(f"  Failed to extract any pages from {pdf_file}")
            else:
                print(f"  No relevant pages detected in {pdf_file}")
                print(f"  API Response: {response_text}")
                
        except Exception as e:
            print(f"  Error processing {pdf_file}: {str(e)}")
    
    print(f"\n--- Processing complete ---")
    print(f"Check the '{output_folder}' folder for extracted PDFs")


if __name__ == "__main__":
    process_all_pdfs()