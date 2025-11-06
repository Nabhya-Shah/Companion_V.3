# 🛠️ Tool Setup Guide

Your Companion AI now has **10 powerful tools** ready to use! Follow this guide to complete setup.

---

## ✅ **Tools Already Working (No Setup Needed)**

1. ✅ **Current Time** - `get_current_time`
2. ✅ **Calculator** - `calculate` 
3. ✅ **Memory Search** - `web_search` (DuckDuckGo fallback)
4. ✅ **Memory Insights** - `memory_insight`
5. ✅ **Wikipedia** - `wikipedia_lookup`
6. ✅ **File Listing** - `list_files`

---

## 🔧 **Quick Setup Required**

### **Step 1: Install Python Packages**

Run this command in your project directory:

```powershell
pip install PyPDF2 Pillow pytesseract python-docx
```

This enables:
- ✅ PDF reading (`read_pdf`)
- ✅ Word document reading (`read_document`)
- ⚠️ Image OCR (`read_image_text`) - **also needs Tesseract binary** (see Step 2)

---

### **Step 2: Install Tesseract OCR (For Image Text Extraction)**

**Windows:**
1. Download: https://github.com/UB-Mannheim/tesseract/wiki
2. Install to: `C:\Program Files\Tesseract-OCR\`
3. Add to PATH or set in code:
   ```python
   pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
   ```

**Mac:**
```bash
brew install tesseract
```

**Linux:**
```bash
sudo apt install tesseract-ocr
```

---

## 🔑 **Optional: API Keys for Enhanced Features**

Add these to your `.env` file for better search and weather:

### **1. OpenWeatherMap (Free - 60 calls/min)**

Get current weather worldwide.

1. Visit: https://openweathermap.org/api
2. Sign up (free)
3. Go to: API Keys section
4. Copy your key
5. Add to `.env`:
   ```
   OPENWEATHER_API_KEY=your_key_here
   ```

**What it enables:**
- Real-time weather for any city
- Temperature, humidity, wind speed, conditions

---

### **2. Brave Search API (Free - 2,000 queries/month)**

Much better web search than DuckDuckGo.

1. Visit: https://brave.com/search/api/
2. Request API access (fill form, usually approved in 1-2 days)
3. Copy your API key
4. Add to `.env`:
   ```
   BRAVE_SEARCH_API_KEY=your_key_here
   ```

**What it enables:**
- Better web search results
- Recent news and current events
- More accurate fact lookup

**Note:** If not configured, falls back to DuckDuckGo (less reliable but works).

---

## 📊 **Tool Status Summary**

| Tool | Status | Requires |
|------|--------|----------|
| `get_current_time` | ✅ Working | Nothing |
| `calculate` | ✅ Working | Nothing |
| `web_search` | ✅ Working | Nothing (uses DuckDuckGo) |
| `memory_insight` | ✅ Working | Nothing |
| `wikipedia_lookup` | ✅ Working | Nothing |
| `list_files` | ✅ Working | Nothing |
| `read_pdf` | ⚠️ Needs Install | `pip install PyPDF2` |
| `read_document` | ⚠️ Needs Install | `pip install python-docx` |
| `read_image_text` | ⚠️ Needs Install | `pip install Pillow pytesseract` + Tesseract binary |
| `get_weather` | 🔑 Optional API | OPENWEATHER_API_KEY in .env |
| `brave_search` | 🔑 Optional API | BRAVE_SEARCH_API_KEY in .env (falls back to DuckDuckGo) |

---

## 🧪 **Testing Your Tools**

After setup, test each tool:

```powershell
# Test PDF reading
python -c "from companion_ai.tools import tool_read_pdf; print(tool_read_pdf('path/to/file.pdf', 1))"

# Test image OCR
python -c "from companion_ai.tools import tool_read_image; print(tool_read_image('path/to/image.png'))"

# Test weather (after API key)
python -c "from companion_ai.tools import tool_weather; print(tool_weather('London'))"

# Test file listing
python -c "from companion_ai.tools import tool_list_files; print(tool_list_files('.', 'pdf'))"
```

Or just chat:
```
"What's the weather in Tokyo?"
"List all PDF files in C:/Users/Documents"
"Read page 5 of homework.pdf and help me with problem 3"
"Extract text from this screenshot"
```

---

## 🎓 **Example Use Cases**

### **Homework Help**
```
"List PDF files in my Documents folder"
"Read page 46 of MathTextbook.pdf"
"What's the formula on that page?"
```

### **Research**
```
"Look up quantum computing on Wikipedia"
"Search for recent AI news"
"What's the weather in the city I'm traveling to?"
```

### **Document Processing**
```
"Read my essay draft and give feedback"
"Extract text from this photo of my notes"
"Calculate 15% of 2,450 for my budget"
```

---

## 🚨 **Troubleshooting**

### **"PDF reading unavailable"**
→ Run: `pip install PyPDF2`

### **"Tesseract OCR not installed"**
→ Install Tesseract binary (see Step 2 above)

### **"Weather service not configured"**
→ Add `OPENWEATHER_API_KEY` to `.env` file

### **Import errors after pip install**
→ Restart Python/server after installing packages

---

## 📝 **Quick Command Reference**

```powershell
# Install all file tools at once
pip install PyPDF2 Pillow pytesseract python-docx

# Check what's installed
pip list | findstr "PyPDF2 Pillow pytesseract python-docx"

# Test if Tesseract is accessible
tesseract --version
```

---

## 🎯 **What's Next?**

Your companion can now:
- ✅ Answer questions with real-time info
- ✅ Help with homework from PDFs
- ✅ Extract text from images/screenshots
- ✅ Read Word documents
- ✅ Get weather and search the web

**Future additions:**
- Vision (analyze images, not just text extraction)
- Computer Use (screen control, automation)
- Streaming responses
- More specialized tools as needed

---

**Need help?** Just ask your companion: *"What tools do you have?"* or *"How can you help with my homework?"*
