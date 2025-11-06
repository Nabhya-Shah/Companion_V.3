"""Tool registry & execution with native function calling support.

Supports both legacy text-based tools (Phase 0) and modern JSON Schema
function calling for Groq native integration.
"""
from __future__ import annotations
import math, datetime, re, os, textwrap, json
from typing import Callable, Dict, Any
from companion_ai import memory as mem

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

@tool('calculate', schema={
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "Perform mathematical calculations. Supports basic operations (+, -, *, /, %, **) and functions like abs(), round(), pow()",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate (e.g., '2 + 2', '15% of 200', 'pow(2, 8)')"
                }
            },
            "required": ["expression"]
        }
    }
})
def tool_calc(expr: str) -> str:
    """Calculate mathematical expressions safely."""
    try:
        # Handle percentage calculations
        expr = expr.lower().replace('% of', '* 0.01 *').replace('%', '* 0.01')
        # extremely restricted eval: digits, operators, parentheses, dots, spaces
        if not all(c in '0123456789+-*/(). %' for c in expr.replace('pow', '').replace('abs', '').replace('round', '')):
            return 'Invalid characters in expression'
        result = eval(expr, {'__builtins__': {'abs': abs, 'round': round, 'pow': pow}, 'math': math}, {})
        return str(result)
    except Exception as e:
        return f'Calculation error: {e}'

@tool('calculate', schema={
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "Perform mathematical calculations. Supports basic operations (+, -, *, /, %, **) and functions like abs(), round(), pow()",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate (e.g., '2 + 2', '15% of 200', 'pow(2, 8)')"
                }
            },
            "required": ["expression"]
        }
    }
})
def tool_calc(expr: str) -> str:
    """Calculate mathematical expressions safely."""
    try:
        # Handle percentage calculations
        expr = expr.lower().replace('% of', '* 0.01 *').replace('%', '* 0.01')
        # extremely restricted eval: digits, operators, parentheses, dots, spaces
        if not all(c in '0123456789+-*/(). %' for c in expr.replace('pow', '').replace('abs', '').replace('round', '')):
            return 'Invalid characters in expression'
        result = eval(expr, {'__builtins__': {'abs': abs, 'round': round, 'pow': pow}, 'math': math}, {})
        return str(result)
    except Exception as e:
        return f'Calculation error: {e}'

@tool('web_search', schema={
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for current information, facts, news, or answers to questions. Use this when the user asks about current events, facts you don't know, or requests to look something up.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query or question to look up"
                }
            },
            "required": ["query"]
        }
    }
})
def tool_search(query: str) -> str:
    """Search web and memory for information."""
    q = (query or '').strip()
    if not q:
        return 'SEARCH_RESULTS (empty query)'
    
    results = []
    
    # 1. Memory search first (fast, personalized)
    mem_hits = mem.search_memory(q, limit=5)
    if mem_hits:
        results.append(f"📚 Memory ({len(mem_hits)} results):")
        for i, hit in enumerate(mem_hits[:3], 1):  # Top 3
            snippet = hit['text']
            if len(snippet) > 120:
                snippet = snippet[:117] + '...'
            results.append(f"  {i}. [{hit['type']}] {snippet}")
    
    # 2. Web search using DuckDuckGo Instant Answer API (no key needed)
    if requests:
        try:
            resp = requests.get(
                'https://api.duckduckgo.com/',
                params={'q': q, 'format': 'json', 'no_html': 1, 'skip_disambig': 1},
                timeout=4.0
            )
            if resp.ok:
                data = resp.json()
                abstract = data.get('AbstractText', '')
                if abstract:
                    abstract = re.sub(r'\s+', ' ', abstract).strip()
                    results.append(f"\n🌐 Web:")
                    results.append(f"  {abstract[:300]}{'...' if len(abstract) > 300 else ''}")
                
                # Also check for instant answer
                answer = data.get('Answer', '')
                if answer:
                    results.append(f"\n✨ Quick Answer: {answer}")
        except Exception as e:
            results.append(f"\n🌐 Web: (unavailable - {str(e)[:50]})")
    
    return '\n'.join(results) if results else f"No results found for '{q}'"

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
    if function_name == 'get_current_time':
        return tool_fn("")
    elif function_name == 'calculate':
        return tool_fn(arguments.get('expression', ''))
    elif function_name == 'web_search':
        return tool_fn(arguments.get('query', ''))
    elif function_name == 'memory_insight':
        return tool_fn("")
    elif function_name == 'get_weather':
        return tool_fn(arguments.get('location', ''))
    elif function_name == 'wikipedia_lookup':
        return tool_fn(arguments.get('query', ''))
    elif function_name == 'brave_search':
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
    else:
        # Fallback: pass first argument or empty string
        first_arg = next(iter(arguments.values()), '') if arguments else ''
        return tool_fn(str(first_arg))

@tool('memory_insight', schema={
    "type": "function",
    "function": {
        "name": "memory_insight",
        "description": "Generate a synthetic insight about the user based on conversation history and stored memories. Use sparingly - only when explicitly asked to reflect or analyze patterns.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
})
def tool_memory_insight(_: str = "") -> str:
    """Generate a quick synthetic insight over last few summaries+insights (read-only)."""
    try:
        # dynamic import inside try to avoid circular dependency during module load
        from companion_ai.llm_interface import generate_groq_response  # type: ignore
        summaries = mem.get_latest_summary(3)
        insights = mem.get_latest_insights(3)
        profile = mem.get_all_profile_facts()
        prompt = (
            "You are generating a SINGLE concise actionable observation about the user based on provided data.\n"
            "Focus on a helpful pattern or preference. Avoid repetition. Max 2 sentences.\n\n"
            f"Profile facts: {profile}\nRecent summaries: {[s['summary_text'] for s in summaries]}\n"
            f"Existing insights: {[i['insight_text'] for i in insights]}\n\nObservation:"
        )
        text = generate_groq_response(prompt) or '(no insight)'
        return text.strip()
    except Exception as e:
        return f"memory_insight error: {e}"

@tool('get_weather', schema={
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather information for a location. Returns temperature, conditions, humidity, wind speed.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name or city,country (e.g., 'Boston', 'London,UK', 'Tokyo,JP')"
                }
            },
            "required": ["location"]
        }
    }
})
def tool_weather(location: str) -> str:
    """Get current weather for a location using WeatherAPI.com."""
    import logging
    logger = logging.getLogger(__name__)
    
    if not requests:
        return "Weather service unavailable (requests library not installed)"
    
    # Get API key from environment
    api_key = os.getenv('WEATHERAPI_KEY')
    logger.info(f"Weather tool called for {location}, API key present: {bool(api_key)}")
    
    if not api_key:
        return "Weather service not configured. Add WEATHERAPI_KEY to .env file. Get free key at: https://www.weatherapi.com/signup.aspx"
    
    try:
        # WeatherAPI.com current weather API
        url = "http://api.weatherapi.com/v1/current.json"
        params = {
            'key': api_key,
            'q': location,
            'aqi': 'no'  # Don't need air quality data
        }
        
        logger.info(f"Calling WeatherAPI for {location}")
        response = requests.get(url, params=params, timeout=5.0)
        logger.info(f"WeatherAPI response status: {response.status_code}")
        
        if response.status_code == 401 or response.status_code == 403:
            return "Invalid weather API key. Check WEATHERAPI_KEY in .env"
        elif response.status_code == 400:
            return f"Location '{location}' not found. Try city name or 'city,country' format."
        elif not response.ok:
            return f"Weather service error: {response.status_code}"
        
        data = response.json()
        
        # Extract key info from WeatherAPI.com response
        location_data = data['location']
        current = data['current']
        
        temp = current['temp_c']
        feels_like = current['feelslike_c']
        humidity = current['humidity']
        condition = current['condition']['text']
        wind_kph = current['wind_kph']
        
        # Format response
        result = (
            f"🌤️ Weather in {location_data['name']}, {location_data['country']}:\n"
            f"Temperature: {temp}°C (feels like {feels_like}°C)\n"
            f"Conditions: {condition}\n"
            f"Humidity: {humidity}%\n"
            f"Wind: {wind_kph} km/h"
        )
        
        logger.info(f"Weather result: {temp}°C {condition}")
        return result
        
    except requests.Timeout:
        return "Weather service timeout. Try again."
    except Exception as e:
        logger.error(f"Weather tool error: {e}")
        return f"Weather lookup error: {str(e)[:100]}"

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

@tool('brave_search', schema={
    "type": "function",
    "function": {
        "name": "brave_search",
        "description": "Search the web using Brave Search API. Returns recent, relevant web results. Better than basic web search for current events, news, detailed information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                }
            },
            "required": ["query"]
        }
    }
})
def tool_brave_search(query: str) -> str:
    """Enhanced web search using Brave Search API (requires API key)."""
    if not requests:
        return "Search unavailable (requests library not installed)"
    
    # Get API key from environment
    api_key = os.getenv('BRAVE_SEARCH_API_KEY')
    if not api_key:
        # Fall back to DuckDuckGo
        return tool_search(query)
    
    try:
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            'Accept': 'application/json',
            'X-Subscription-Token': api_key
        }
        params = {
            'q': query,
            'count': 5
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=5.0)
        
        if not response.ok:
            # Fall back to DuckDuckGo
            return tool_search(query)
        
        data = response.json()
        results = []
        
        # Check memory first
        mem_hits = mem.search_memory(query, limit=3)
        if mem_hits:
            results.append(f"📚 Memory ({len(mem_hits)} results):")
            for i, hit in enumerate(mem_hits, 1):
                snippet = hit['text']
                if len(snippet) > 100:
                    snippet = snippet[:97] + '...'
                results.append(f"  {i}. {snippet}")
        
        # Add web results
        if 'web' in data and 'results' in data['web']:
            web_results = data['web']['results'][:3]
            results.append(f"\n🌐 Web Results:")
            for i, result in enumerate(web_results, 1):
                title = result.get('title', 'No title')
                description = result.get('description', '')
                if len(description) > 150:
                    description = description[:147] + '...'
                results.append(f"  {i}. {title}")
                if description:
                    results.append(f"     {description}")
        
        return '\n'.join(results) if results else f"No results for '{query}'"
        
    except Exception as e:
        # Fall back to DuckDuckGo
        return tool_search(query)

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

__all__ = ['list_tools', 'run_tool', 'get_function_schemas', 'execute_function_call']