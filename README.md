# Medical Document Processor - Streamlit App

A web-based interface for processing medical documents and extracting structured data using AI.

## Features

- **Simple Web Interface**: Upload files and process with a single click
- **Multiple Input Formats**: Support for single PDF or ZIP files containing multiple PDFs
- **Automated Processing**: Handles PDF splitting and data extraction automatically
- **Field Definition Support**: Uses Excel files to define extraction rules
- **CSV Output**: Downloads results as structured CSV files

## Setup

### Prerequisites

1. **Python 3.8+** installed on your system
2. **Tesseract OCR** installed (required for PDF text extraction)
3. **Google GenAI API Key** configured

### Installation

1. **Clone or download** this repository
2. **Install dependencies**:
   ```bash
   pip install -r streamlit_requirements.txt
   pip install -r requirements.txt
   ```

3. **Install Tesseract OCR**:
   - **macOS**: `brew install tesseract`
   - **Ubuntu/Debian**: `sudo apt-get install tesseract-ocr`
   - **Windows**: Download from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki)

4. **Set up Google GenAI API**:
   ```bash
   export GOOGLE_API_KEY="your-api-key-here"
   ```

## Usage

### Running the App

1. **Start the Streamlit app**:
   ```bash
   streamlit run streamlit_app.py
   ```

2. **Open your browser** and go to `http://localhost:8501`

### Using the Interface

1. **Upload Patient Documents**:
   - **Single PDF**: Upload a PDF containing multiple patient records
   - **ZIP File**: Upload a ZIP containing individual patient PDFs

2. **Upload Field Definitions**:
   - Upload an Excel file (e.g., `DUN.xlsx`) containing field extraction rules
   - The app will automatically detect the group name from the filename

3. **Process Documents**:
   - Click the "Process Documents" button
   - Wait for processing to complete (progress bar will show status)

4. **Download Results**:
   - Click "Download CSV Results" to get the extracted data
   - Preview the results in the app before downloading

## File Structure

```
├── streamlit_app.py              # Main Streamlit application
├── utils/
│   ├── __init__.py
│   ├── file_processor.py         # Handles file uploads and processing
│   └── extraction_wrapper.py     # Wraps existing extraction scripts
├── current/                      # Original processing scripts
│   ├── 1-split_pdf_by_detections.py
│   ├── 2-extract_info.py
│   ├── field_definitions.py
│   └── instructions/             # Excel files with field definitions
├── requirements.txt              # Original dependencies
├── streamlit_requirements.txt    # Streamlit-specific dependencies
└── README.md
```

## Supported Groups

The app supports various medical groups with predefined filter strings:

- **DUN**: Patient Address
- **SIO**: Anesthesia Billing, Address 1, Address 2, Gender
- **SIO-STL**: Patient Demographics
- **STA-DGSS**: Patient Demographics Form
- **APO-UTP**: Billing and Compliance Report
- **APO-UPM**: Billing and Compliance Report
- **APO-CVO**: Patient Registration Data
- **GAP-UMSC**: Patient Registration Data
- **KAP-CYP**: Patent Demographic Form
- **KAP-ASC**: PatientData
- **WPA**: Anesthesia Billing, Address 1, Address 2, Gender

## Troubleshooting

### Common Issues

1. **Tesseract not found**:
   - Ensure Tesseract is installed and in your PATH
   - On macOS: `brew install tesseract`
   - On Ubuntu: `sudo apt-get install tesseract-ocr`

2. **Google API Key not set**:
   - Set the environment variable: `export GOOGLE_API_KEY="your-key"`
   - Or create a `.env` file with: `GOOGLE_API_KEY=your-key`

3. **Processing timeout**:
   - Large files may take longer to process
   - Check the console for detailed error messages

4. **No PDFs found in ZIP**:
   - Ensure the ZIP file contains PDF files
   - Check that the PDFs are not in nested folders

### Error Messages

- **"No PDF files found in ZIP"**: The uploaded ZIP doesn't contain PDF files
- **"Processing timed out"**: The file is too large or processing is taking too long
- **"Field definitions not found"**: The Excel file format is incorrect

## Deployment

### Local Deployment
```bash
streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0
```

### Cloud Deployment
The app can be deployed to:
- **Streamlit Cloud**: Connect your GitHub repository
- **Heroku**: Use the provided `Procfile` and `setup.sh`
- **AWS/GCP**: Deploy as a containerized application

## Security Notes

- The app processes files in temporary directories that are cleaned up after processing
- No files are permanently stored on the server
- API keys should be kept secure and not committed to version control

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the console output for error messages
3. Ensure all dependencies are properly installed 