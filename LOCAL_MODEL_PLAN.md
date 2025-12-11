# Local Model Strategy (RTX 5080 Edition)

## 🖥️ Hardware Profile
*   **GPU:** NVIDIA RTX 5080
*   **VRAM:** 16 GB
*   **Target:** High-speed, low-latency local inference for privacy and autonomy.

## 🧠 Model Selection
With 16GB VRAM, we can run high-quality quantized models entirely on GPU without offloading to system RAM.

### 1. Primary Agent (Tools & Computer Control)
*   **Model:** `llama3.1:8b` (Quantization: Q8_0 or FP16)
*   **Why:** The 8B parameter size is the "sweet spot" for speed and instruction following. At Q8/FP16, it fits easily (~10GB) and retains maximum intelligence.
*   **Role:** Handling background tasks, computer control, and tool execution.
*   **Ollama Tag:** `llama3.1:latest`

### 2. Vision (The "Eyes")
*   **Model:** `minicpm-v` (8B) or `llava:13b`
*   **Why:** `minicpm-v` is currently SOTA for small vision models, beating GPT-4V on some benchmarks. `llava:13b` is a reliable fallback if we need more "world knowledge".
*   **Role:** Analyzing screenshots for the Computer Agent.
*   **Ollama Tag:** `minicpm-v`

### 3. Heavy Reasoning (Optional/Deep Thought)
*   **Model:** `qwen2.5:14b` or `mistral-nemo:12b`
*   **Why:** These mid-sized models offer a significant jump in reasoning capability over 8B models while still fitting comfortably in 16GB VRAM (at Q4_K_M).
*   **Role:** Complex planning, coding tasks, or "Deep Work" jobs.
*   **Ollama Tag:** `qwen2.5:14b`

## 🏗️ Architecture

### Hybrid Approach
*   **Chat/Personality:** Continues on **Groq (Llama 3 70B/8B)** for instant speed and massive context (until local context caching improves).
*   **Computer Control:** **Local (Ollama)**. This prevents sending screenshots and sensitive desktop data to the cloud.
*   **Background Jobs:** **Local (Ollama)**. Allows the agent to work indefinitely without racking up API costs.

### Implementation Status
*   [x] `local_llm.py`: Backend abstraction created.
*   [x] `OllamaClientWrapper`: Implemented to mimic OpenAI API for tool use.
*   [x] `job_manager.py`: Updated to prefer local models for background tasks.
*   [ ] **Configuration:** Need to update `config.py` to allow user to specify model names easily.
*   [ ] **Vision Integration:** Switch `vision_manager.py` to use local Ollama vision instead of GPT-4o/Groq (if applicable).

## 🛠️ Setup Instructions
1.  **Install Ollama:** [Download](https://ollama.com/download)
2.  **Pull Models:**
    ```powershell
    ollama pull llama3.1
    ollama pull minicpm-v
    ollama pull qwen2.5:14b
    ```
3.  **Verify:** Run `python tools/check_local_models.py` (To be created).
