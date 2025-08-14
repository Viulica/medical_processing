#!/usr/bin/env python3

# Test script to verify subscription ID cleaning
import re

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
        # Keep only alphanumeric characters and common ID separators
        cleaned = re.sub(r'[^a-zA-Z0-9\-_\.]', '', cleaned)
    
    return cleaned

# Test cases
test_cases = [
    ("Primary Subsc ID", "ABC123!@#$%^&*()"),
    ("Secondary Subsc ID", "XYZ789-_-_"),
    ("Primary Subsc ID", "123-456-789"),
    ("Secondary Subsc ID", "ABC@#$%^&*()XYZ"),
    ("Patient Name", "John Doe"),  # Should not be affected
    ("Primary Subsc ID", "ABC-123_456.789"),
    ("Secondary Subsc ID", "XYZ 789"),  # Space should be removed
]

print("Testing subscription ID cleaning:")
print("=" * 50)

for field_name, value in test_cases:
    cleaned = clean_field_value(value, field_name)
    print(f"Field: {field_name}")
    print(f"  Original: '{value}'")
    print(f"  Cleaned:  '{cleaned}'")
    print()

print("✅ Test completed!") 