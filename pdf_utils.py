"""
PDF Utility Module for Resume Parsing
Uses pypdf to extract text from uploaded PDF files.
"""

from pypdf import PdfReader
from io import BytesIO
from typing import Union
from werkzeug.datastructures import FileStorage


def extract_text_from_pdf(file: Union[FileStorage, BytesIO, str]) -> str:
    """
    Extract text content from a PDF file.
    
    Args:
        file: A FileStorage object (Flask upload), BytesIO object, or file path string.
        
    Returns:
        Extracted text as a single string.
    """
    try:
        if isinstance(file, str):
            # File path provided
            reader = PdfReader(file)
        else:
            # FileStorage or BytesIO object
            reader = PdfReader(file)
        
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        
        return "\n".join(text_parts).strip()
    
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF: {str(e)}")


def extract_text_from_multiple_pdfs(files: list) -> list:
    """
    Extract text from multiple PDF files.
    
    Args:
        files: List of FileStorage objects.
        
    Returns:
        List of dictionaries with filename and extracted text.
    """
    results = []
    for file in files:
        try:
            text = extract_text_from_pdf(file)
            results.append({
                "filename": file.filename,
                "text": text,
                "success": True,
                "error": None
            })
        except Exception as e:
            results.append({
                "filename": file.filename,
                "text": "",
                "success": False,
                "error": str(e)
            })
    return results
