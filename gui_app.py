#!/usr/bin/env python3
"""
Modern GUI for Companion AI
Features:
- Clean chat interface
- Toggle for thinking tags
- Scrollable conversation history
- Modern styling
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import re
from companion_ai.llm_interface import generate_response
from companion_ai import memory as db
from companion_ai.tts_manager import tts_manager
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CompanionGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Companion AI")
        self.root.geometry("800x600")
        self.root.configure(bg='#2b2b2b')
        
        # Session storage for end-of-conversation processing
        self.conversation_log = []
        
        # Settings
        self.show_thinking = tk.BooleanVar(value=False)
        self.tts_enabled = tk.BooleanVar(value=tts_manager.is_enabled)
        
        self.setup_ui()
        
        # Handle window closing to process session memory
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def setup_ui(self):
        """Setup the user interface with modern styling"""
        # Configure modern color scheme
        self.colors = {
            'bg_primary': '#1a1a2e',      # Dark blue-purple
            'bg_secondary': '#16213e',     # Darker blue
            'bg_accent': '#0f3460',        # Blue accent
            'text_primary': '#ffffff',     # White text
            'text_secondary': '#b8c5d6',  # Light blue-gray
            'accent_blue': '#4fc3f7',     # Bright blue
            'accent_purple': '#9c27b0',   # Purple
            'accent_green': '#4caf50',    # Green
            'user_bubble': '#4fc3f7',     # User message color
            'ai_bubble': '#9c27b0',       # AI message color
            'system_text': '#ffa726'      # Orange for system messages
        }
        
        # Set root background
        self.root.configure(bg=self.colors['bg_primary'])
        
        # Main frame with gradient-like effect
        main_frame = tk.Frame(self.root, bg=self.colors['bg_primary'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Configure modern ttk style
        style = ttk.Style()
        style.theme_use('clam')
        
        # Custom styles
        style.configure('Modern.TFrame', background=self.colors['bg_secondary'])
        style.configure('Header.TLabel', 
                       background=self.colors['bg_primary'], 
                       foreground=self.colors['text_primary'],
                       font=('Segoe UI', 18, 'bold'))
        style.configure('Modern.TCheckbutton',
                       background=self.colors['bg_secondary'],
                       foreground=self.colors['text_primary'],
                       font=('Segoe UI', 10))
        style.configure('Modern.TCombobox',
                       fieldbackground=self.colors['bg_accent'],
                       background=self.colors['bg_secondary'],
                       foreground=self.colors['text_primary'])
        style.configure('Modern.TButton',
                       background=self.colors['accent_blue'],
                       foreground='white',
                       font=('Segoe UI', 11, 'bold'),
                       borderwidth=0)
        
        # Header frame with modern styling
        header_frame = tk.Frame(main_frame, bg=self.colors['bg_secondary'], height=60)
        header_frame.pack(fill=tk.X, pady=(0, 15))
        header_frame.pack_propagate(False)
        
        # Title with gradient-like effect
        title_label = tk.Label(header_frame, 
                              text="🤖 Companion AI", 
                              font=('Segoe UI', 20, 'bold'),
                              bg=self.colors['bg_secondary'],
                              fg=self.colors['accent_blue'])
        title_label.pack(side=tk.LEFT, padx=20, pady=15)
        
        # Settings frame with modern background
        settings_frame = tk.Frame(header_frame, bg=self.colors['bg_secondary'])
        settings_frame.pack(side=tk.RIGHT, padx=20, pady=10)
        
        # Voice selection dropdown with modern styling
        voice_label = tk.Label(settings_frame, 
                              text="Voice:", 
                              bg=self.colors['bg_secondary'],
                              fg=self.colors['text_secondary'],
                              font=('Segoe UI', 10))
        voice_label.pack(side=tk.RIGHT, padx=(10, 5))
        
        self.voice_var = tk.StringVar(value=tts_manager.current_voice)
        voice_dropdown = ttk.Combobox(settings_frame, 
                                     textvariable=self.voice_var,
                                     values=tts_manager.get_available_voices(),
                                     state="readonly",
                                     width=25,
                                     style='Modern.TCombobox')
        voice_dropdown.pack(side=tk.RIGHT, padx=(0, 15))
        voice_dropdown.bind('<<ComboboxSelected>>', self.change_voice)
        
        # TTS toggle with modern styling
        tts_status = "🔊" if tts_manager.speech_key != "your_azure_key_here" else "❌"
        tts_check = tk.Checkbutton(settings_frame, 
                                  text=f"{tts_status} TTS", 
                                  variable=self.tts_enabled,
                                  command=self.toggle_tts,
                                  bg=self.colors['bg_secondary'],
                                  fg=self.colors['text_primary'],
                                  selectcolor=self.colors['bg_accent'],
                                  activebackground=self.colors['bg_secondary'],
                                  activeforeground=self.colors['accent_blue'],
                                  font=('Segoe UI', 10, 'bold'))
        tts_check.pack(side=tk.RIGHT, padx=(10, 15))
        
        # Show thinking toggle with modern styling
        thinking_check = tk.Checkbutton(settings_frame, 
                                       text="Show AI Thinking", 
                                       variable=self.show_thinking,
                                       bg=self.colors['bg_secondary'],
                                       fg=self.colors['text_primary'],
                                       selectcolor=self.colors['bg_accent'],
                                       activebackground=self.colors['bg_secondary'],
                                       activeforeground=self.colors['accent_purple'],
                                       font=('Segoe UI', 10))
        thinking_check.pack(side=tk.RIGHT, padx=(10, 0))
        
        # Chat display area with modern styling
        chat_frame = tk.Frame(main_frame, bg=self.colors['bg_secondary'], relief='flat', bd=2)
        chat_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        self.chat_display = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            width=80,
            height=25,
            font=('Segoe UI', 11),
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_primary'],
            insertbackground=self.colors['accent_blue'],
            state=tk.DISABLED,
            relief='flat',
            bd=0,
            padx=15,
            pady=15
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # Configure modern text tags for styling
        self.chat_display.tag_configure("user", 
                                       foreground=self.colors['user_bubble'], 
                                       font=('Segoe UI', 11, 'bold'))
        self.chat_display.tag_configure("ai", 
                                       foreground=self.colors['ai_bubble'], 
                                       font=('Segoe UI', 11, 'bold'))
        self.chat_display.tag_configure("thinking", 
                                       foreground=self.colors['system_text'], 
                                       font=('Segoe UI', 10, 'italic'))
        self.chat_display.tag_configure("system", 
                                       foreground=self.colors['system_text'], 
                                       font=('Segoe UI', 10))
        
        # Input frame with modern styling
        input_frame = tk.Frame(main_frame, bg=self.colors['bg_primary'])
        input_frame.pack(fill=tk.X)
        
        # Message input with modern styling
        self.message_entry = tk.Text(
            input_frame,
            height=3,
            font=('Segoe UI', 11),
            bg=self.colors['bg_accent'],
            fg=self.colors['text_primary'],
            insertbackground=self.colors['accent_blue'],
            wrap=tk.WORD,
            relief='flat',
            bd=0,
            padx=15,
            pady=10
        )
        self.message_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 15))
        
        # Send button with modern styling
        self.send_button = tk.Button(
            input_frame,
            text="Send 🚀",
            command=self.send_message,
            width=12,
            height=3,
            font=('Segoe UI', 11, 'bold'),
            bg=self.colors['accent_blue'],
            fg='white',
            activebackground=self.colors['accent_purple'],
            activeforeground='white',
            relief='flat',
            bd=0,
            cursor='hand2'
        )
        self.send_button.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind Enter key
        self.message_entry.bind('<Control-Return>', lambda e: self.send_message())
        self.message_entry.bind('<Shift-Return>', lambda e: None)  # Allow Shift+Enter for new lines
        
        # Status bar with modern styling
        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Label(main_frame, 
                             textvariable=self.status_var, 
                             font=('Segoe UI', 9),
                             bg=self.colors['bg_primary'],
                             fg=self.colors['text_secondary'])
        status_bar.pack(fill=tk.X, pady=(10, 0))
        
        # Welcome message
        self.add_system_message("Welcome to Companion AI! Type your message and press Ctrl+Enter to send.")
        
    def add_message(self, sender, message, tag):
        """Add a message to the chat display"""
        self.chat_display.config(state=tk.NORMAL)
        
        # Add timestamp and sender
        timestamp = ""  # You can add timestamp if needed
        self.chat_display.insert(tk.END, f"{sender}: ", tag)
        self.chat_display.insert(tk.END, f"{message}\n\n")
        
        # Auto-scroll to bottom
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
        
    def add_system_message(self, message):
        """Add a system message"""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, f"System: {message}\n\n", "system")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
        
    def process_ai_response(self, response):
        """Process AI response and handle thinking tags"""
        if not self.show_thinking.get():
            # Remove thinking tags
            response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
            response = response.strip()
        else:
            # Style thinking tags differently
            parts = re.split(r'(<think>.*?</think>)', response, flags=re.DOTALL)
            processed_response = ""
            
            for part in parts:
                if part.startswith('<think>') and part.endswith('</think>'):
                    thinking_content = part[7:-8]  # Remove <think> tags
                    processed_response += f"\n[Thinking: {thinking_content}]\n"
                else:
                    processed_response += part
            
            response = processed_response.strip()
        
        return response
        
    def send_message(self):
        """Send user message and get AI response - simple approach"""
        message = self.message_entry.get("1.0", tk.END).strip()
        if not message:
            return
            
        # Clear input
        self.message_entry.delete("1.0", tk.END)
        
        # Add user message to chat
        self.add_message("You", message, "user")
        
        # Disable send button and show thinking status
        self.send_button.config(state=tk.DISABLED)
        self.status_var.set("AI is thinking...")
        
        # Simple conversation processing
        def process_response():
            try:
                # Get current memory context (completely minimal for clean conversation)
                memory_context = {
                    "profile": {},      # Don't load profile facts during conversation
                    "summaries": [],    # Don't load summaries during conversation
                    "insights": []      # Don't load insights during conversation
                }
                
                # Generate response normally
                response = generate_response(message, memory_context)
                
                # Process response (handle thinking tags)
                processed_response = self.process_ai_response(response)
                
                # Store conversation exchange for end-of-session processing
                from datetime import datetime
                self.conversation_log.append({
                    "user": message,
                    "ai": response,
                    "timestamp": datetime.now().isoformat()
                })
                
                # Also write to temporary chat log file for review
                self._write_to_chat_log(message, response)
                
                # Update UI
                self.root.after(0, lambda: self.handle_ai_response(processed_response))
                
            except Exception as e:
                logger.error(f"Error generating response: {e}")
                self.root.after(0, lambda: self.handle_error(str(e)))
        
        # Start background thread
        threading.Thread(target=process_response, daemon=True).start()
        
    def handle_ai_response(self, ai_response):
        """Handle AI response in main thread"""
        self.add_message("AI", ai_response, "ai")
        
        # Speak the response if TTS is enabled
        if self.tts_enabled.get():
            tts_manager.speak_text(ai_response, blocking=False)
        
        self.send_button.config(state=tk.NORMAL)
        self.status_var.set("Ready")
        
    def handle_error(self, error_message):
        """Handle errors in main thread"""
        self.add_system_message(f"Error: {error_message}")
        self.send_button.config(state=tk.NORMAL)
        self.status_var.set("Error occurred")
    
    def toggle_tts(self):
        """Toggle TTS on/off"""
        if self.tts_enabled.get():
            # Enable TTS
            if tts_manager.speech_key and tts_manager.speech_region:
                tts_manager.is_enabled = True
                self.add_system_message("🔊 Text-to-Speech enabled")
                # Test TTS with a short message using current voice
                tts_manager.speak_text("TTS is now enabled", blocking=False)
            else:
                self.tts_enabled.set(False)  # Revert checkbox
                self.add_system_message("❌ TTS unavailable - check Azure credentials in .env file")
        else:
            # Disable TTS
            tts_manager.is_enabled = False
            self.add_system_message("🔇 Text-to-Speech disabled")
    
    def change_voice(self, event=None):
        """Change TTS voice when dropdown selection changes"""
        new_voice = self.voice_var.get()
        if tts_manager.set_voice(new_voice):
            self.add_system_message(f"🎤 Voice changed to: {new_voice}")
            # Test the new voice
            if tts_manager.is_enabled:
                tts_manager.speak_text("Hi, this is my new voice!", blocking=False)
        else:
            self.add_system_message(f"❌ Failed to change voice to: {new_voice}")
    
    def on_closing(self):
        """Handle window closing - process session memory"""
        if self.conversation_log:
            logger.info(f"Processing session memory for {len(self.conversation_log)} exchanges")
            self.process_session_memory()
        else:
            logger.info("No conversation to process")
        
        logger.info("Companion AI session ended")
        self.root.destroy()
    
    def process_session_memory(self):
        """Process entire conversation session with Memory AI"""
        try:
            from companion_ai.memory_ai import groq_memory_client
            
            if not groq_memory_client:
                logger.warning("Memory AI client not available")
                return
            
            # Create full conversation text for analysis
            conversation_text = self._format_conversation_for_analysis()
            
            # Analyze entire session importance
            session_importance = self._analyze_session_importance(conversation_text)
            logger.info(f"🧠 Session importance: {session_importance:.2f}")
            
            if session_importance > 0.3:
                # Generate session summary
                session_summary = self._generate_session_summary(conversation_text)
                if session_summary:
                    db.add_summary(session_summary, session_importance)
                    logger.info("📝 Session summary stored")
                
                # Extract profile facts from entire session
                session_facts = self._extract_session_facts(conversation_text)
                for key, data in session_facts.items():
                    db.upsert_profile_fact(key, data['value'], data['confidence'])
                    logger.info(f"👤 Profile fact stored: {key}")
                
                # Generate session insights
                session_insights = self._generate_session_insights(conversation_text)
                if session_insights:
                    db.add_insight(session_insights, "session", session_importance)
                    logger.info("💡 Session insights stored")
            else:
                logger.info("🧠 Low importance session - minimal storage")
                
        except Exception as e:
            logger.error(f"Session memory processing failed: {e}")
    
    def _format_conversation_for_analysis(self) -> str:
        """Format conversation log for Memory AI analysis"""
        formatted = "CONVERSATION SESSION:\n\n"
        for i, exchange in enumerate(self.conversation_log, 1):
            formatted += f"Exchange {i}:\n"
            formatted += f"User: {exchange['user']}\n"
            formatted += f"AI: {exchange['ai']}\n\n"
        return formatted
    
    def _analyze_session_importance(self, conversation_text: str) -> float:
        """Analyze overall session importance"""
        from companion_ai.memory_ai import groq_memory_client
        
        prompt = f"""Analyze this entire conversation session and rate its overall importance for long-term memory (0.0-1.0):

{conversation_text}

Consider:
- Personal information revealed across the session
- Relationship building and rapport
- Unique insights about the user
- Technical discussions or learning
- Overall conversation depth and value

Return only a decimal score (e.g., 0.7):"""

        try:
            response = groq_memory_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=50
            )
            
            import re
            score_text = response.choices[0].message.content.strip()
            match = re.search(r'(\d*\.?\d+)', score_text)
            if match:
                return min(max(float(match.group(1)), 0.0), 1.0)
        except Exception as e:
            logger.error(f"Session importance analysis failed: {e}")
        
        return 0.4  # Default moderate importance
    
    def _generate_session_summary(self, conversation_text: str) -> str:
        """Generate summary of entire session"""
        from companion_ai.memory_ai import groq_memory_client
        
        prompt = f"""Summarize this conversation session in 2-3 sentences, focusing on key topics and user characteristics:

{conversation_text}

Summary:"""

        try:
            response = groq_memory_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=150
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Session summary generation failed: {e}")
            return ""
    
    def _extract_session_facts(self, conversation_text: str) -> dict:
        """Extract profile facts from entire session"""
        from companion_ai.memory_ai import groq_memory_client
        
        prompt = f"""Extract personal facts about the user from this entire conversation session. Return as JSON:

{conversation_text}

Format: {{"fact_name": {{"value": "fact_value", "confidence": 0.8}}}}

JSON:"""

        try:
            response = groq_memory_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=300
            )
            
            import json, re
            facts_text = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', facts_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"Session fact extraction failed: {e}")
        
        return {}
    
    def _generate_session_insights(self, conversation_text: str) -> str:
        """Generate insights about user from entire session"""
        from companion_ai.memory_ai import groq_memory_client
        
        prompt = f"""Based on this entire conversation session, generate a brief insight about the user's personality, interests, or communication style:

{conversation_text}

Insight (1-2 sentences):"""

        try:
            response = groq_memory_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=150
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Session insight generation failed: {e}")
            return ""
    
    def _write_to_chat_log(self, user_message: str, ai_response: str):
        """Write conversation to temporary chat log file for review"""
        try:
            # Use a simple temp file that gets overwritten each session
            log_file = "temp_chat_session.txt"
            
            # Write to file (append mode for session)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"User: {user_message}\n")
                f.write(f"AI: {ai_response}\n")
                f.write("-" * 50 + "\n")
            
        except Exception as e:
            logger.error(f"Failed to write chat log: {e}")

def main():
    """Main function to run the GUI"""
    root = tk.Tk()
    app = CompanionGUI(root)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        messagebox.showerror("Error", f"An error occurred: {e}")

if __name__ == "__main__":
    main()