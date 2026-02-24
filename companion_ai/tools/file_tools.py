"""File operation tools — PDF, image OCR, Word docs, directory listing, file search."""
from __future__ import annotations

import os
from typing import Dict

from companion_ai.tools.registry import tool

# Graceful imports for optional dependencies
try:
    import pypdf
except ImportError:
    pypdf = None

try:
    from PIL import Image
    import pytesseract
except ImportError:
    Image = None
    pytesseract = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

@tool('read_pdf', schema={
    "type": "function",
    "function": {
        "name": "read_pdf",
        "description": "Extract and read text from a PDF file. Useful for homework, textbooks, research papers. Provide the full file path.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the PDF file (e.g., 'C:/Users/docs/homework.pdf' or 'textbook.pdf')"
                },
                "page_number": {
                    "type": "integer",
                    "description": "Optional: specific page number to read (1-indexed). If not provided, reads first 3 pages."
                }
            },
            "required": ["file_path"]
        }
    }
})
def tool_read_pdf(file_path: str, page_number: int | None = None) -> str:
    """Read text from a PDF file."""
    if not pypdf:
        return "PDF reading unavailable. Install with: pip install pypdf"

    if not os.path.exists(file_path):
        return f"File not found: {file_path}"

    try:
        with open(file_path, 'rb') as file:
            pdf_reader = pypdf.PdfReader(file)
            total_pages = len(pdf_reader.pages)

            if page_number:
                if page_number < 1 or page_number > total_pages:
                    return f"Page {page_number} out of range. PDF has {total_pages} pages."
                page = pdf_reader.pages[page_number - 1]
                text = page.extract_text()
                return f"📄 PDF: {os.path.basename(file_path)} - Page {page_number}/{total_pages}\n\n{text}"
            else:
                pages_to_read = min(3, total_pages)
                texts = []
                for i in range(pages_to_read):
                    page = pdf_reader.pages[i]
                    page_text = page.extract_text()
                    if page_text.strip():
                        texts.append(f"=== Page {i+1} ===\n{page_text}")
                result = '\n\n'.join(texts)
                return f"📄 PDF: {os.path.basename(file_path)} ({total_pages} pages total, showing first {pages_to_read})\n\n{result}"

    except Exception as e:
        return f"Error reading PDF: {str(e)[:200]}"


# ---------------------------------------------------------------------------
# Image OCR
# ---------------------------------------------------------------------------

@tool('read_image_text', schema={
    "type": "function",
    "function": {
        "name": "read_image_text",
        "description": "Extract text from an image using OCR (Optical Character Recognition). Works with screenshots, photos of documents, handwritten notes (if clear), math problems.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to image file (jpg, png, bmp, etc.)"
                }
            },
            "required": ["file_path"]
        }
    }
})
def tool_read_image(file_path: str) -> str:
    """Extract text from an image using OCR."""
    if not Image or not pytesseract:
        return "Image OCR unavailable. Install with: pip install Pillow pytesseract\nAlso install Tesseract: https://github.com/tesseract-ocr/tesseract"

    if not os.path.exists(file_path):
        return f"Image not found: {file_path}"

    try:
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img)

        if not text.strip():
            return f"No text detected in image: {os.path.basename(file_path)}"

        return f"📷 Image OCR: {os.path.basename(file_path)}\n\n{text}"

    except pytesseract.TesseractNotFoundError:
        return "Tesseract OCR not installed. Download from: https://github.com/tesseract-ocr/tesseract/releases"
    except Exception as e:
        return f"Error reading image: {str(e)[:200]}"


# ---------------------------------------------------------------------------
# Word Documents
# ---------------------------------------------------------------------------

@tool('read_document', schema={
    "type": "function",
    "function": {
        "name": "read_document",
        "description": "Read text from Word documents (.docx). Useful for essays, assignments, reports.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to .docx file"
                }
            },
            "required": ["file_path"]
        }
    }
})
def tool_read_docx(file_path: str) -> str:
    """Read text from a Word document."""
    if not DocxDocument:
        return "Word document reading unavailable. Install with: pip install python-docx"

    if not os.path.exists(file_path):
        return f"Document not found: {file_path}"

    try:
        doc = DocxDocument(file_path)
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]

        if not paragraphs:
            return f"No text found in document: {os.path.basename(file_path)}"

        text = '\n\n'.join(paragraphs)
        if len(text) > 3000:
            text = text[:2997] + '...'

        return f"📝 Word Document: {os.path.basename(file_path)}\n\n{text}"

    except Exception as e:
        return f"Error reading document: {str(e)[:200]}"


# ---------------------------------------------------------------------------
# Directory listing / file search
# ---------------------------------------------------------------------------

@tool('list_files', schema={
    "type": "function",
    "function": {
        "name": "list_files",
        "description": "List files in a directory. Useful for finding homework files, PDFs, images before reading them.",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory path to list (e.g., 'C:/Users/Documents' or '.' for current)"
                },
                "file_type": {
                    "type": "string",
                    "description": "Optional: filter by extension (e.g., 'pdf', 'png', 'docx')"
                }
            },
            "required": ["directory"]
        }
    }
})
def tool_list_files(directory: str, file_type: str | None = None) -> str:
    """List files in a directory with optional filtering."""
    if not os.path.exists(directory):
        return f"Directory not found: {directory}"

    if not os.path.isdir(directory):
        return f"Not a directory: {directory}"

    try:
        files = []
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if os.path.isfile(item_path):
                if file_type:
                    if item.lower().endswith(f'.{file_type.lower()}'):
                        files.append(item)
                else:
                    files.append(item)

        if not files:
            filter_msg = f" (filtered by .{file_type})" if file_type else ""
            return f"No files found in {directory}{filter_msg}"

        by_ext: Dict[str, list[str]] = {}
        for f in files:
            ext = f.split('.')[-1].lower() if '.' in f else 'no extension'
            if ext not in by_ext:
                by_ext[ext] = []
            by_ext[ext].append(f)

        result = [f"📁 Files in {directory}:\n"]
        for ext, file_list in sorted(by_ext.items()):
            result.append(f"\n{ext.upper()} files ({len(file_list)}):")
            for f in sorted(file_list)[:20]:
                result.append(f"  - {f}")
            if len(file_list) > 20:
                result.append(f"  ... and {len(file_list) - 20} more")

        return '\n'.join(result)

    except Exception as e:
        return f"Error listing directory: {str(e)[:200]}"


@tool('find_file', schema={
    "type": "function",
    "function": {
        "name": "find_file",
        "description": "Search for files by name or keyword in common user directories (Downloads, Documents, Desktop). Returns matching files with full paths.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename or keyword to search for (e.g., 'Companion AI', 'report', 'homework')"
                },
                "file_type": {
                    "type": "string",
                    "description": "Optional: file extension to filter (e.g., 'pdf', 'docx', 'png')"
                }
            },
            "required": ["filename"]
        }
    }
})
def tool_find_file(filename: str, file_type: str | None = None) -> str:
    """Search for files in common user directories."""
    from pathlib import Path

    user_home = os.path.expanduser("~")
    search_dirs = [
        os.path.join(user_home, "Downloads"),
        os.path.join(user_home, "Documents"),
        os.path.join(user_home, "Desktop"),
    ]

    matches = []
    search_term = filename.lower()

    for directory in search_dirs:
        if not os.path.exists(directory):
            continue

        try:
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                if not os.path.isfile(item_path):
                    continue

                item_lower = item.lower()
                if search_term in item_lower:
                    if file_type and not item_lower.endswith(f'.{file_type.lower()}'):
                        continue

                    size = os.path.getsize(item_path)
                    size_str = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f} MB"

                    matches.append({
                        'name': item,
                        'path': item_path,
                        'size': size_str,
                        'dir': os.path.basename(directory)
                    })
        except Exception:
            continue

    if not matches:
        type_msg = f" (*.{file_type})" if file_type else ""
        return f"No files matching '{filename}'{type_msg} found in Downloads, Documents, or Desktop."

    result = [f"Found {len(matches)} file(s) matching '{filename}':"]
    for m in matches[:10]:
        result.append(f"\n📄 {m['name']}")
        result.append(f"   Location: {m['dir']}/")
        result.append(f"   Size: {m['size']}")
        result.append(f"   Full path: {m['path']}")

    if len(matches) > 10:
        result.append(f"\n... and {len(matches) - 10} more matches")

    return '\n'.join(result)
