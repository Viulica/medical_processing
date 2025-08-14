# Deployment Guide - Medical Document Processor

## Free Hosting Options

### 1. Streamlit Cloud (Recommended - Easiest)

**Steps:**
1. **Create a GitHub repository** and push your code:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
   git push -u origin main
   ```

2. **Go to [share.streamlit.io](https://share.streamlit.io)**
3. **Sign in with GitHub**
4. **Click "New app"**
5. **Select your repository and branch**
6. **Set the main file path to:** `streamlit_app.py`
7. **Click "Deploy"**

**Pros:** 
- Completely free
- Automatic deployments from GitHub
- No server management
- Built specifically for Streamlit

**Cons:**
- Limited to 1GB RAM
- May timeout on large PDF processing

### 2. Railway (Alternative)

**Steps:**
1. **Go to [railway.app](https://railway.app)**
2. **Sign in with GitHub**
3. **Click "New Project" → "Deploy from GitHub repo"**
4. **Select your repository**
5. **Add environment variables:**
   - `GOOGLE_API_KEY`: Your Google GenAI API key
6. **Deploy**

**Pros:**
- Free tier available
- More resources than Streamlit Cloud
- Better for heavy processing

### 3. Render (Alternative)

**Steps:**
1. **Go to [render.com](https://render.com)**
2. **Sign up and connect GitHub**
3. **Click "New Web Service"**
4. **Select your repository**
5. **Configure:**
   - **Build Command:** `pip install -r requirements_deploy.txt`
   - **Start Command:** `streamlit run streamlit_app.py --server.port $PORT --server.address 0.0.0.0`
6. **Add environment variables**
7. **Deploy**

## Required Files for Deployment

Make sure these files are in your repository:

```
your-repo/
├── streamlit_app.py          # Main app file
├── requirements.txt          # Python dependencies (for local development)
├── requirements_deploy.txt   # Deployment-optimized dependencies
├── utils/                    # Utility modules
│   ├── __init__.py
│   ├── file_processor.py
│   └── extraction_wrapper.py
├── current/                  # Original scripts
│   ├── 1-split_pdf_by_detections.py
│   ├── 2-extract_info.py
│   ├── field_definitions.py
│   └── extraction_prompt.txt
└── README.md
```

## Environment Variables

You'll need to set these environment variables in your hosting platform:

- `GOOGLE_API_KEY`: Your Google GenAI API key

## Important Notes

### For Streamlit Cloud:
- **File size limits**: 200MB per file upload
- **Processing time**: May timeout on large PDFs
- **Memory**: Limited to 1GB RAM

### For Railway/Render:
- **Better performance** for large files
- **More memory** available
- **Longer processing times** allowed

## Common Deployment Issues

### PyMuPDF Compilation Error
If you see errors like:
```
ld -r -b binary -z noexecstack -o build/PyMuPDF-x86_64-shared-tesseract-release/...
Error during processing dependencies!
```

**Solution:**
1. Use `requirements_deploy.txt` instead of `requirements.txt`
2. This file contains newer versions with pre-compiled wheels
3. For Streamlit Cloud, rename `requirements_deploy.txt` to `requirements.txt`

### Alternative Fix:
If the above doesn't work, try using a different PDF library:
```bash
# Replace PyMuPDF with a lighter alternative
pip uninstall PyMuPDF
pip install pdfplumber
```

## Security Considerations

1. **API Keys**: Never commit API keys to your repository
2. **File Uploads**: Consider adding file size and type validation
3. **Rate Limiting**: Consider adding rate limiting for production use

## Troubleshooting

### Common Issues:

1. **Import Errors**: Make sure all dependencies are in `requirements.txt`
2. **File Not Found**: Ensure all required files are in the repository
3. **API Key Issues**: Check environment variables are set correctly
4. **Timeout Errors**: Consider using Railway/Render for large file processing
5. **PyMuPDF Compilation**: Use `requirements_deploy.txt` or newer versions

### Testing Locally Before Deployment:

```bash
# Test the app locally
streamlit run streamlit_app.py

# Test with environment variables
GOOGLE_API_KEY=your_key_here streamlit run streamlit_app.py
```

## Cost Comparison

| Platform | Free Tier | Paid Plans | Best For |
|----------|-----------|------------|----------|
| Streamlit Cloud | ✅ Free | $10/month | Small apps, quick deployment |
| Railway | ✅ Free | $5/month | Medium apps, better performance |
| Render | ✅ Free | $7/month | Large apps, production use |

## Recommendation

**Start with Streamlit Cloud** for simplicity, then migrate to Railway if you need better performance for large PDF processing. 