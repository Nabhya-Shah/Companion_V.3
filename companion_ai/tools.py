"""Tool registry & execution with native function calling support.

Supports both legacy text-based tools (Phase 0) and modern JSON Schema
function calling for Groq native integration.
"""
from __future__ import annotations
import datetime, re, os, json
from typing import Callable, Dict, Any
from companion_ai import memory as mem
try:
    from companion_ai.memory_v2 import search_memories
except ImportError:
    search_memories = None

# Graceful imports for optional dependencies
try:
    import requests
except ImportError:
    requests = None

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

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

ToolFn = Callable[[str], str]

# Legacy text-based tools
_TOOLS: Dict[str, ToolFn] = {}

# Modern function calling schemas (JSON Schema format for Groq)
_FUNCTION_SCHEMAS: Dict[str, Dict[str, Any]] = {}

def tool(name: str, schema: Dict[str, Any] | None = None):
    """Decorator to register both legacy and modern function-calling tools.
    
    Args:
        name: Tool identifier
        schema: Optional JSON Schema for native function calling
    """
    def wrap(fn: ToolFn):
        _TOOLS[name] = fn
        if schema:
            _FUNCTION_SCHEMAS[name] = schema
        return fn
    return wrap

# ============================================================================
# TOOL DEFINITIONS
# ============================================================================

@tool('get_current_time', schema={
    "type": "function",
    "function": {
        "name": "get_current_time",
        "description": "Get the current date and time in ISO format",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
})
def tool_time(_: str = "") -> str:
    """Get current time in ISO format."""
    return datetime.datetime.now().isoformat(timespec='seconds')

def list_tools() -> list[str]:
    """List all available tool names."""
    return sorted(_TOOLS.keys())

def run_tool(name: str, arg: str) -> str:
    """Execute a tool by name with string argument (legacy interface)."""
    fn = _TOOLS.get(name)
    if not fn:
        return f'Unknown tool: {name}'
    return fn(arg)

def get_function_schemas() -> list[Dict[str, Any]]:
    """Get all function calling schemas for Groq native integration."""
    return list(_FUNCTION_SCHEMAS.values())

def execute_function_call(function_name: str, arguments: Dict[str, Any]) -> str:
    """Execute a function call from Groq's native function calling.
    
    Args:
        function_name: Name of the function to call
        arguments: Dictionary of arguments parsed from JSON
        
    Returns:
        String result from the function
    """
    # Map native function names to tool functions
    tool_fn = _TOOLS.get(function_name)
    if not tool_fn:
        return f'Unknown function: {function_name}'
    
    # Handle different function signatures
    elif function_name == 'get_current_time':
        return tool_fn("")
    elif function_name == 'memory_search':
        return tool_fn(arguments.get('query', ''))
    # memory_insight removed - V5 cleanup
    elif function_name == 'wikipedia_lookup':
        return tool_fn(arguments.get('query', ''))
    elif function_name == 'read_pdf':
        return tool_fn(arguments.get('file_path', ''), arguments.get('page_number'))
    elif function_name == 'read_image_text':
        return tool_fn(arguments.get('file_path', ''))
    elif function_name == 'read_document':
        return tool_fn(arguments.get('file_path', ''))
    elif function_name == 'list_files':
        return tool_fn(arguments.get('directory', '.'), arguments.get('file_type'))
    elif function_name == 'find_file':
        return tool_fn(arguments.get('filename', ''), arguments.get('file_type'))
    elif function_name == 'look_at_screen':
        return tool_fn(arguments.get('prompt', 'What is on the screen?'))
    elif function_name == 'use_computer':
        return tool_fn(action=arguments.get('action'), text=arguments.get('text'))
    else:
        # Fallback: pass first argument or empty string
        first_arg = next(iter(arguments.values()), '') if arguments else ''
        return tool_fn(str(first_arg))

@tool('memory_search', schema={
    "type": "function",
    "function": {
        "name": "memory_search",
        "description": "Search the user's long-term memory (vector database) for specific facts, preferences, or past conversations. Use this when you need to recall something specific that isn't in the immediate context.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find relevant memories."
                }
            },
            "required": ["query"]
        }
    }
})
def tool_memory_search(query: str) -> str:
    """Search Mem0 vector database for relevant memories."""
    if not search_memories:
        return "Memory search unavailable (Mem0 not loaded)."
    
    try:
        results = search_memories(query, limit=5)
        if not results:
            return f"No memories found for '{query}'."
        
        output = [f"🧠 Memory Search Results for '{query}':"]
        for i, res in enumerate(results, 1):
            # Handle both dict (Mem0 v2) and object return types if any
            text = res.get('memory', res.get('text', str(res)))
            score = res.get('score', 0)
            date = res.get('created_at', '')[:10] if res.get('created_at') else 'Unknown date'
            output.append(f"{i}. {text} (Date: {date}, Relevance: {score:.2f})")
            
        return "\n".join(output)
    except Exception as e:
        return f"Error searching memory: {str(e)}"

# memory_insight tool removed - V5 cleanup (consolidated to memory_search)

@tool('wikipedia_lookup', schema={
    "type": "function",
    "function": {
        "name": "wikipedia_lookup",
        "description": "Look up factual information on Wikipedia. Returns a concise summary of the topic. Best for facts, definitions, historical info.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Topic or term to look up (e.g., 'Python programming', 'Albert Einstein', 'World War 2')"
                }
            },
            "required": ["query"]
        }
    }
})
def tool_wikipedia(query: str) -> str:
    """Look up information on Wikipedia."""
    if not requests:
        return "Wikipedia lookup unavailable (requests library not installed)"
    
    try:
        # Wikipedia API - search for article
        search_url = "https://en.wikipedia.org/w/api.php"
        headers = {
            'User-Agent': 'CompanionAI/1.0 (Educational Assistant)'
        }
        search_params = {
            'action': 'opensearch',
            'search': query,
            'limit': 1,
            'format': 'json'
        }
        
        search_resp = requests.get(search_url, params=search_params, headers=headers, timeout=5.0)
        search_data = search_resp.json()
        
        if not search_data[1]:  # No results
            return f"No Wikipedia article found for '{query}'"
        
        title = search_data[1][0]
        
        # Get article summary
        summary_params = {
            'action': 'query',
            'prop': 'extracts',
            'exintro': True,
            'explaintext': True,
            'titles': title,
            'format': 'json'
        }
        
        summary_resp = requests.get(search_url, params=summary_params, headers=headers, timeout=5.0)
        summary_data = summary_resp.json()
        
        pages = summary_data['query']['pages']
        page = next(iter(pages.values()))
        
        if 'extract' not in page:
            return f"Could not retrieve summary for '{title}'"
        
        extract = page['extract']
        
        # Limit to ~500 chars
        if len(extract) > 500:
            extract = extract[:497] + '...'
        
        return f"📖 Wikipedia - {title}:\n\n{extract}"
        
    except requests.Timeout:
        return "Wikipedia lookup timeout. Try again."
    except Exception as e:
        return f"Wikipedia error: {str(e)[:100]}"

# ============================================================================
# FILE READING TOOLS
# ============================================================================

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
    if not PyPDF2:
        return "PDF reading unavailable. Install with: pip install PyPDF2"
    
    if not os.path.exists(file_path):
        return f"File not found: {file_path}"
    
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            total_pages = len(pdf_reader.pages)
            
            if page_number:
                # Read specific page
                if page_number < 1 or page_number > total_pages:
                    return f"Page {page_number} out of range. PDF has {total_pages} pages."
                
                page = pdf_reader.pages[page_number - 1]  # 0-indexed
                text = page.extract_text()
                
                return f"📄 PDF: {os.path.basename(file_path)} - Page {page_number}/{total_pages}\n\n{text}"
            else:
                # Read first 3 pages
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
        # Open and process image
        img = Image.open(file_path)
        
        # Extract text using Tesseract OCR
        text = pytesseract.image_to_string(img)
        
        if not text.strip():
            return f"No text detected in image: {os.path.basename(file_path)}"
        
        return f"📷 Image OCR: {os.path.basename(file_path)}\n\n{text}"
        
    except pytesseract.TesseractNotFoundError:
        return "Tesseract OCR not installed. Download from: https://github.com/tesseract-ocr/tesseract/releases"
    except Exception as e:
        return f"Error reading image: {str(e)[:200]}"

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
        
        # Extract all paragraphs
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        
        if not paragraphs:
            return f"No text found in document: {os.path.basename(file_path)}"
        
        text = '\n\n'.join(paragraphs)
        
        # Limit output
        if len(text) > 3000:
            text = text[:2997] + '...'
        
        return f"📝 Word Document: {os.path.basename(file_path)}\n\n{text}"
        
    except Exception as e:
        return f"Error reading document: {str(e)[:200]}"

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
                # Filter by file type if specified
                if file_type:
                    if item.lower().endswith(f'.{file_type.lower()}'):
                        files.append(item)
                else:
                    files.append(item)
        
        if not files:
            filter_msg = f" (filtered by .{file_type})" if file_type else ""
            return f"No files found in {directory}{filter_msg}"
        
        # Group by extension
        by_ext: Dict[str, list[str]] = {}
        for f in files:
            ext = f.split('.')[-1].lower() if '.' in f else 'no extension'
            if ext not in by_ext:
                by_ext[ext] = []
            by_ext[ext].append(f)
        
        result = [f"📁 Files in {directory}:\n"]
        for ext, file_list in sorted(by_ext.items()):
            result.append(f"\n{ext.upper()} files ({len(file_list)}):")
            for f in sorted(file_list)[:20]:  # Limit to 20 per type
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
    import os
    from pathlib import Path
    
    # Common directories to search
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
                
                # Check if filename matches
                item_lower = item.lower()
                if search_term in item_lower:
                    # Check file type if specified
                    if file_type and not item_lower.endswith(f'.{file_type.lower()}'):
                        continue
                    
                    # Get file size
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
    
    # Format results
    result = [f"Found {len(matches)} file(s) matching '{filename}':"]
    for m in matches[:10]:  # Limit to 10 results
        result.append(f"\n📄 {m['name']}")
        result.append(f"   Location: {m['dir']}/")
        result.append(f"   Size: {m['size']}")
        result.append(f"   Full path: {m['path']}")
    
    if len(matches) > 10:
        result.append(f"\n... and {len(matches) - 10} more matches")
    
    return '\n'.join(result)

@tool('look_at_screen', schema={
    "type": "function",
    "function": {
        "name": "look_at_screen",
        "description": "Take a screenshot of the user's current screen and analyze it. Use this when the user asks you to 'look at this', 'see my screen', 'what am I doing', or asks for help with something visible on their monitor.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Specific question about the screen content (e.g., 'What code is this?', 'Help me with this error', 'Describe the image'). Defaults to general description."
                }
            },
            "required": []
        }
    }
})
def tool_look_at_screen(prompt: str = "What is on the screen?") -> str:
    """Analyze the current screen content."""
    try:
        from companion_ai.vision_manager import vision_manager
        return vision_manager.analyze_current_screen(prompt)
    except Exception as e:
        return f"Error analyzing screen: {e}"

# consult_compound_system tool removed - V5 cleanup (120B has built-in search)

@tool('use_computer', schema={
    "type": "function",
    "function": {
        "name": "use_computer",
        "description": "DIRECTLY CONTROL the computer. Use this to OPEN applications, CLICK buttons, TYPE text, or navigate the UI. Do not just advise the user to do it—DO IT yourself. Example: to open Notepad, click the 'Start' button or type 'Notepad'.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action to perform: 'click' (click element), 'type' (text), 'press' (key), 'launch' (open app via Run), 'scroll_up', 'scroll_down'",
                    "enum": ["click", "type", "press", "launch", "scroll_up", "scroll_down"]
                },
                "text": {
                    "type": "string",
                    "description": "If action='click', the description of the element (e.g., 'Submit Button', 'File Menu'). If action='type', the text to type."
                }
            },
            "required": ["action"]
        }
    }
})
def tool_use_computer(action: str, text: str = "") -> str:
    """Execute computer control actions."""
    from companion_ai.core import config as core_config
    if not core_config.ENABLE_COMPUTER_USE:
        return "Computer Use is disabled in configuration."

    try:
        from companion_ai.computer_agent import computer_agent
        
        if action == "click":
            if not text: return "Error: 'text' (element description) is required for click action."
            return computer_agent.click_element(text)
            
        elif action == "type":
            if not text: return "Error: 'text' (content to type) is required for type action."
            return computer_agent.type_text(text, enter=True)
            
        elif action == "press":
            return computer_agent.press_key(text)
            
        elif action == "launch":
            return computer_agent.launch_app(text)
            
        elif action == "scroll_up":
            return computer_agent.scroll("up")
            
        elif action == "scroll_down":
            return computer_agent.scroll("down")
            
        else:
            return f"Unknown action: {action}"
            
    except Exception as e:
        return f"Computer Use Error: {e}"

__all__ = ['list_tools', 'run_tool', 'get_function_schemas', 'execute_function_call']