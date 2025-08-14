#!/usr/bin/env python3
"""
Simple test script to verify the Streamlit app components work correctly.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add current directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'current'))

def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")
    
    try:
        from utils.file_processor import process_uploaded_files, extract_group_name_from_excel
        from utils.extraction_wrapper import run_extraction_pipeline, get_filter_strings_for_group
        print("✅ All utility modules imported successfully")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    
    try:
        import streamlit as st
        import pandas as pd
        import openpyxl
        print("✅ All dependencies imported successfully")
    except ImportError as e:
        print(f"❌ Dependency import error: {e}")
        return False
    
    return True

def test_group_name_extraction():
    """Test group name extraction from Excel filenames."""
    print("\nTesting group name extraction...")
    
    from utils.file_processor import extract_group_name_from_excel
    
    # Mock uploaded file object
    class MockFile:
        def __init__(self, name):
            self.name = name
    
    test_cases = [
        ("DUN.xlsx", "DUN"),
        ("SIO-STL.xlsx", "SIO-STL"),
        ("APO-UTP.xlsx", "APO-UTP"),
        ("test_file.xlsx", "test_file")
    ]
    
    for filename, expected in test_cases:
        mock_file = MockFile(filename)
        result = extract_group_name_from_excel(mock_file)
        if result == expected:
            print(f"✅ {filename} -> {result}")
        else:
            print(f"❌ {filename} -> {result} (expected {expected})")
            return False
    
    return True

def test_filter_strings():
    """Test filter string mapping for different groups."""
    print("\nTesting filter string mapping...")
    
    from utils.extraction_wrapper import get_filter_strings_for_group
    
    test_cases = [
        ("DUN", ['Patient Address']),
        ("SIO", ['Anesthesia Billing', 'Address 1', 'Address 2', 'Gender']),
        ("APO-UTP", ['Billing and Compliance Report'])
    ]
    
    for group, expected in test_cases:
        result = get_filter_strings_for_group(group)
        if result == expected:
            print(f"✅ {group} -> {result}")
        else:
            print(f"❌ {group} -> {result} (expected {expected})")
            return False
    
    return True

def test_directory_structure():
    """Test that required directories and files exist."""
    print("\nTesting directory structure...")
    
    required_files = [
        "streamlit_app.py",
        "utils/file_processor.py",
        "utils/extraction_wrapper.py",
        "current/1-split_pdf_by_detections.py",
        "current/2-extract_info.py",
        "current/field_definitions.py"
    ]
    
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} - Missing!")
            return False
    
    return True

def main():
    """Run all tests."""
    print("🧪 Testing Medical Document Processor Streamlit App\n")
    
    tests = [
        test_imports,
        test_group_name_extraction,
        test_filter_strings,
        test_directory_structure
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print(f"❌ Test {test.__name__} failed")
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The app should work correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Please check the issues above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 