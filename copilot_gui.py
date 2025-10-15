#!/usr/bin/env python3
"""
Copilot-style GUI for Companion AI
Inspired by GitHub Copilot's clean, modern interface
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import re
from datetime import datetime
from pathlib import Path
from companion_ai.llm_interface import generate_response
from companion_ai import memory as db
from companion_ai.tts_manager import tts_manager
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CopilotCompanionGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Companion AI")
        self.root.geometry("900x750")  # Increased height to ensure input area is visible
        self.root.minsize(700, 600)  # Increased minimum size to prevent UI elements from being hidden
        
        # Modern dark theme colors (Copilot-inspired)
        self.colors = {
            'bg_primary': '#0d1117',      # GitHub dark background
            'bg_secondary': '#161b22',     # Slightly lighter
            'bg_tertiary': '#21262d',      # Card/panel background
            'bg_input': '#0d1117',         # Input background
            'border': '#30363d',           # Border color
            'text_primary': '#f0f6fc',     # Primary text
            'text_secondary': '#8b949e',   # Secondary text
            'text_muted': '#6e7681',       # Muted text
            'accent_blue': '#58a6ff',      # GitHub blue
            'accent_purple': '#a5a5ff',    # Purple accent
            'accent_green': '#3fb950',     # Success green
            'accent_orange': '#f85149',    # Warning/error
            'user_bubble': '#58a6ff',      # User messages
            'ai_bubble': '#a5a5ff',        # AI messages
            'button_hover': '#1f6feb'      # Button hover
        }
        
        self.root.configure(bg=self.colors['bg_primary'])
        
        # Session storage
        self.conversation_log = []
        self.show_thinking = tk.BooleanVar(value=False)
        self.tts_enabled = tk.BooleanVar(value=tts_manager.is_enabled)
        
        # Chat log file setup
        self.chat_log_dir = Path("data/chat_logs")
        self.chat_log_dir.mkdir(parents=True, exist_ok=True)
        self.session_start = datetime.now()
        self.chat_log_file = self.chat_log_dir / f"chat_{self.session_start.strftime('%Y%m%d_%H%M%S')}.txt"
        self.initialize_chat_log()
        
        # Model selection - Using smartest model for natural conversation
        self.current_model = "openai/gpt-oss-120b"  # 120B parameter model for better conversation quality
        
        # Persona selection
        self.current_persona = "Companion"  # Adaptive persona
        
        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Bind window resize event for responsive design
        self.root.bind('<Configure>', self.on_window_resize)
        
        # Store references for responsive design
        self.action_buttons = []
        self.current_window_width = 900
        
    def setup_ui(self):
        """Setup the Copilot-inspired interface"""
        # Main container with padding
        main_container = tk.Frame(self.root, bg=self.colors['bg_primary'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Header section
        self.create_header(main_container)
        
        # Quick actions (Copilot-style buttons) - BEFORE chat area
        self.create_quick_actions(main_container)
        
        # Chat area
        self.create_chat_area(main_container)
        
        # Input area
        self.create_input_area(main_container)
        
        # Welcome message
        self.show_welcome_message()
        
    def create_header(self, parent):
        """Create the header with title and settings"""
        header_frame = tk.Frame(parent, bg=self.colors['bg_primary'])
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Main header content
        header_content = tk.Frame(header_frame, bg=self.colors['bg_primary'])
        header_content.pack(fill=tk.X)
        
        # Left side - Title and subtitle
        title_frame = tk.Frame(header_content, bg=self.colors['bg_primary'])
        title_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Title (responsive font size)
        self.title_label = tk.Label(
            title_frame,
            text="Hi there. What should we dive into today?",
            font=('Segoe UI', 24, 'normal'),
            bg=self.colors['bg_primary'],
            fg=self.colors['text_primary']
        )
        self.title_label.pack(anchor='w')
        
        # Subtitle
        self.subtitle_label = tk.Label(
            title_frame,
            text="Your AI companion is ready to help with anything you need.",
            font=('Segoe UI', 12),
            bg=self.colors['bg_primary'],
            fg=self.colors['text_secondary']
        )
        self.subtitle_label.pack(anchor='w', pady=(5, 0))
        
        # Right side - Settings
        settings_frame = tk.Frame(header_content, bg=self.colors['bg_primary'])
        settings_frame.pack(side=tk.RIGHT, padx=(20, 0))
        
        # Voice selection
        voice_label = tk.Label(
            settings_frame,
            text="Voice:",
            font=('Segoe UI', 10),
            bg=self.colors['bg_primary'],
            fg=self.colors['text_secondary']
        )
        voice_label.pack(anchor='w')
        
        self.voice_var = tk.StringVar(value="Phoebe Dragon HD")
        voice_options = ["Phoebe Dragon HD", "Ava Dragon HD"]
        self.voice_dropdown = tk.OptionMenu(
            settings_frame,
            self.voice_var,
            *voice_options,
            command=self.change_voice
        )
        self.voice_dropdown.configure(
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_primary'],
            activebackground=self.colors['bg_tertiary'],
            activeforeground=self.colors['text_primary'],
            highlightthickness=0,
            relief='flat',
            font=('Segoe UI', 9),
            width=15
        )
        # Style the dropdown menu
        self.voice_dropdown['menu'].configure(
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_primary'],
            activebackground=self.colors['accent_blue'],
            activeforeground='white'
        )
        self.voice_dropdown.pack(anchor='w', pady=(2, 10))
        
        # Model selection
        model_label = tk.Label(
            settings_frame,
            text="Model:",
            font=('Segoe UI', 10),
            bg=self.colors['bg_primary'],
            fg=self.colors['text_secondary']
        )
        model_label.pack(anchor='w')
        
        self.model_var = tk.StringVar(value="Kimi K2")
        model_options = ["DeepSeek R1", "Llama 70B", "Kimi K2"]
        self.model_dropdown = tk.OptionMenu(
            settings_frame,
            self.model_var,
            *model_options,
            command=self.change_model
        )
        self.model_dropdown.configure(
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_primary'],
            activebackground=self.colors['bg_tertiary'],
            activeforeground=self.colors['text_primary'],
            highlightthickness=0,
            relief='flat',
            font=('Segoe UI', 9),
            width=15
        )
        # Style the dropdown menu
        self.model_dropdown['menu'].configure(
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_primary'],
            activebackground=self.colors['accent_blue'],
            activeforeground='white'
        )
        self.model_dropdown.pack(anchor='w', pady=(2, 10))
        
        # Persona selection
        persona_label = tk.Label(
            settings_frame,
            text="Persona:",
            font=('Segoe UI', 10),
            bg=self.colors['bg_primary'],
            fg=self.colors['text_secondary']
        )
        persona_label.pack(anchor='w')
        
        self.persona_var = tk.StringVar(value="Aether")
        persona_options = ["Aether", "Lilith"]
        self.persona_dropdown = tk.OptionMenu(
            settings_frame,
            self.persona_var,
            *persona_options,
            command=self.change_persona
        )
        self.persona_dropdown.configure(
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_primary'],
            activebackground=self.colors['bg_tertiary'],
            activeforeground=self.colors['text_primary'],
            highlightthickness=0,
            relief='flat',
            font=('Segoe UI', 9),
            width=15
        )
        # Style the dropdown menu
        self.persona_dropdown['menu'].configure(
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_primary'],
            activebackground=self.colors['accent_blue'],
            activeforeground='white'
        )
        self.persona_dropdown.pack(anchor='w', pady=(2, 0))
        
    def create_chat_area(self, parent):
        """Create the main chat display area"""
        # Chat container with border
        chat_container = tk.Frame(
            parent, 
            bg=self.colors['bg_tertiary'],
            relief='solid',
            bd=1,
            highlightbackground=self.colors['border'],
            highlightthickness=1
        )
        chat_container.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # Chat display
        self.chat_display = scrolledtext.ScrolledText(
            chat_container,
            wrap=tk.WORD,
            font=('Segoe UI', 11),
            bg=self.colors['bg_tertiary'],
            fg=self.colors['text_primary'],
            insertbackground=self.colors['accent_blue'],
            state=tk.DISABLED,
            relief='flat',
            bd=0,
            padx=20,
            pady=20,
            selectbackground=self.colors['bg_secondary'],
            height=12  # Reduced height to ensure input area is always visible
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True)
        
        # Configure text tags for modern styling
        self.chat_display.tag_configure("user", 
                                       foreground=self.colors['user_bubble'], 
                                       font=('Segoe UI', 11, 'bold'))
        self.chat_display.tag_configure("ai", 
                                       foreground=self.colors['ai_bubble'], 
                                       font=('Segoe UI', 11))
        self.chat_display.tag_configure("thinking", 
                                       foreground=self.colors['text_muted'], 
                                       font=('Segoe UI', 10, 'italic'))
        self.chat_display.tag_configure("system", 
                                       foreground=self.colors['accent_green'], 
                                       font=('Segoe UI', 10))
        
    def create_quick_actions(self, parent):
        """Create Copilot-style quick action buttons"""
        self.actions_frame = tk.Frame(parent, bg=self.colors['bg_primary'])
        self.actions_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Quick action buttons (better organized)
        self.actions_data = [
            # First row - Memory & Analysis
            [
                ("View Memory", self.review_memory),
                ("Get Insights", self.get_insights),
                ("Export Memory", self.export_memory),
                ("Clear Memory", self.clear_memory)
            ],
            # Second row - Chat & Settings
            [
                ("Summarize Chat", self.summarize_chat),
                ("Voice Settings", self.voice_settings),
                ("Clear Chat", self.clear_chat)
            ]
        ]
        
        self.action_buttons = []
        self.row_frames = []
        
        for row_idx, row in enumerate(self.actions_data):
            row_frame = tk.Frame(self.actions_frame, bg=self.colors['bg_primary'])
            row_frame.pack(fill=tk.X, pady=(5 if row_idx > 0 else 0, 0))
            self.row_frames.append(row_frame)
            
            row_buttons = []
            for action_text, action_cmd in row:
                btn = tk.Button(
                    row_frame,
                    text=action_text,
                    command=action_cmd,
                    font=('Segoe UI', 10),
                    bg=self.colors['bg_secondary'],
                    fg=self.colors['text_secondary'],
                    activebackground=self.colors['button_hover'],
                    activeforeground=self.colors['text_primary'],
                    relief='flat',
                    bd=0,
                    padx=15,
                    pady=8,
                    cursor='hand2',
                    wraplength=120  # Allow text wrapping for smaller buttons
                )
                btn.pack(side=tk.LEFT, padx=(0, 10))
                row_buttons.append(btn)
                
                # Hover effects
                def on_enter(e, button=btn):
                    button.configure(bg=self.colors['button_hover'], fg=self.colors['text_primary'])
                def on_leave(e, button=btn):
                    button.configure(bg=self.colors['bg_secondary'], fg=self.colors['text_secondary'])
                    
                btn.bind("<Enter>", on_enter)
                btn.bind("<Leave>", on_leave)
            
            self.action_buttons.append(row_buttons)
    
    def create_input_area(self, parent):
        """Create the input area with Copilot-style design"""
        # Input container
        input_container = tk.Frame(
            parent,
            bg=self.colors['bg_tertiary'],
            relief='solid',
            bd=1,
            highlightbackground=self.colors['border'],
            highlightthickness=1
        )
        input_container.pack(fill=tk.X)
        
        # Input frame
        input_frame = tk.Frame(input_container, bg=self.colors['bg_tertiary'])
        input_frame.pack(fill=tk.X, padx=15, pady=15)
        
        # Message input (Copilot-style)
        self.message_entry = tk.Text(
            input_frame,
            height=3,
            font=('Segoe UI', 11),
            bg=self.colors['bg_input'],
            fg=self.colors['text_primary'],
            insertbackground=self.colors['accent_blue'],
            wrap=tk.WORD,
            relief='flat',
            bd=0,
            padx=15,
            pady=10
        )
        self.message_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Placeholder text
        self.add_placeholder()
        
        # Button container
        button_frame = tk.Frame(input_frame, bg=self.colors['bg_tertiary'])
        button_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(15, 0))
        
        # Voice button (rounded style)
        self.voice_btn = tk.Button(
            button_frame,
            text="♪",
            command=self.toggle_voice,
            font=('Segoe UI', 14),
            bg=self.colors['bg_secondary'],
            fg=self.colors['text_secondary'],
            activebackground=self.colors['button_hover'],
            activeforeground=self.colors['text_primary'],
            relief='flat',
            bd=0,
            width=4,
            height=2,
            cursor='hand2'
        )
        self.voice_btn.pack(pady=(5, 10))
        
        # Send button (larger, rounded style)
        self.send_btn = tk.Button(
            button_frame,
            text="Send",
            command=self.send_message,
            font=('Segoe UI', 11, 'bold'),
            bg=self.colors['accent_blue'],
            fg='white',
            activebackground=self.colors['button_hover'],
            activeforeground='white',
            relief='flat',
            bd=0,
            width=6,
            height=2,
            cursor='hand2'
        )
        self.send_btn.pack()
        
        # Bind events
        self.message_entry.bind('<Control-Return>', lambda e: self.send_message())
        self.message_entry.bind('<Return>', self.on_enter_key)  # Handle Enter key
        self.message_entry.bind('<FocusIn>', self.on_entry_focus_in)
        self.message_entry.bind('<FocusOut>', self.on_entry_focus_out)
        
        # Add keyboard shortcuts
        self.root.bind('<Control-n>', lambda e: self.clear_chat())
        self.root.bind('<Control-m>', lambda e: self.review_memory())
        self.root.bind('<Escape>', lambda e: self.message_entry.focus())
        
    def add_placeholder(self):
        """Add placeholder text to input"""
        self.placeholder_text = "Message Companion AI"
        self.message_entry.insert("1.0", self.placeholder_text)
        self.message_entry.configure(fg=self.colors['text_muted'])
        
    def on_entry_focus_in(self, event):
        """Handle input focus in"""
        if self.message_entry.get("1.0", tk.END).strip() == self.placeholder_text:
            self.message_entry.delete("1.0", tk.END)
            self.message_entry.configure(fg=self.colors['text_primary'])
            
    def on_entry_focus_out(self, event):
        """Handle input focus out"""
        # Only add placeholder if the field is completely empty and we haven't sent a message yet
        if not self.message_entry.get("1.0", tk.END).strip() and not hasattr(self, 'message_sent'):
            self.message_entry.insert("1.0", self.placeholder_text)
            self.message_entry.configure(fg=self.colors['text_muted'])
    
    def initialize_chat_log(self):
        """Initialize the chat log file with session info"""
        try:
            with open(self.chat_log_file, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write(f"COMPANION AI CHAT LOG\n")
                f.write(f"Session Started: {self.session_start.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")
            logger.info(f"Chat log initialized at: {self.chat_log_file}")
        except Exception as e:
            logger.error(f"Failed to initialize chat log: {e}")
    
    def append_to_chat_log(self, sender, message):
        """Append a message to the chat log file in real-time"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            with open(self.chat_log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {sender}:\n")
                f.write(f"{message}\n\n")
        except Exception as e:
            logger.error(f"Failed to append to chat log: {e}")
    
    def show_welcome_message(self):
        """Show welcome message in chat"""
        welcome_text = f"""Welcome to Companion AI!

I'm here to help you with anything you need. You can:
• Have natural conversations with me
• Ask questions about any topic
• Get help with coding, writing, or problem-solving
• Use the quick action buttons above for common tasks

📝 Chat log: {self.chat_log_file.name}

Try one of the quick actions above, or just start typing below!"""
        
        self.add_message("System", welcome_text, "system")
    
    def add_message(self, sender, message, tag):
        """Add a message to the chat display with improved formatting"""
        self.chat_display.config(state=tk.NORMAL)
        
        # Add some spacing between messages
        if self.chat_display.get("1.0", tk.END).strip():
            self.chat_display.insert(tk.END, "\n\n")
        
        # Add sender with modern styling and timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M")
        
        if sender == "You":
            self.chat_display.insert(tk.END, f"You • {timestamp}\n", "user")
        elif sender == "AI":
            self.chat_display.insert(tk.END, f"Companion AI • {timestamp}\n", "ai")
        else:
            self.chat_display.insert(tk.END, f"{sender} • {timestamp}\n", tag)
        
        # Add message content with better formatting
        formatted_message = message.replace('\n\n\n', '\n\n')  # Clean up excessive newlines
        self.chat_display.insert(tk.END, f"{formatted_message}\n")
        
        # Auto-scroll to bottom
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
    
    def send_message(self):
        """Send user message and get AI response"""
        message = self.message_entry.get("1.0", tk.END).strip()
        
        # Check if it's placeholder text or empty
        if not message or message == self.placeholder_text:
            return
        
        # Stop any currently playing TTS
        if tts_manager.is_enabled:
            tts_manager.stop_current_speech()
            
        # Clear input and leave it empty (no placeholder)
        self.message_entry.delete("1.0", tk.END)
        self.message_entry.configure(fg=self.colors['text_primary'])
        
        # Mark that a message has been sent
        self.message_sent = True
        
        # Add user message to chat
        self.add_message("You", message, "user")
        
        # Log user message to file
        self.append_to_chat_log("You", message)
        
        # Disable send button and show thinking
        self.send_btn.config(state=tk.DISABLED, text="...")
        
        def process_response():
            try:
                # Get actual memory context from database
                from companion_ai import memory as db
                
                # Build recent conversation context from GUI history
                recent_turns = []
                for turn in self.conversation_log[-3:]:  # Last 3 turns
                    recent_turns.append(f"User: {turn['user']}")
                    recent_turns.append(f"AI: {turn['ai']}")
                
                # Add current message as context
                recent_context = "\n".join(recent_turns) if recent_turns else ""
                
                # Build full context including recent conversation
                memory_context = {
                    "profile": db.get_all_profile_facts(),
                    "summaries": db.get_latest_summary(3),
                    "insights": db.get_latest_insights(3),
                    "recent_conversation": recent_context
                }
                
                # Generate response with selected model and persona
                response = generate_response(message, memory_context, self.current_model, self.current_persona)
                
                # Store conversation
                from datetime import datetime
                self.conversation_log.append({
                    "user": message,
                    "ai": response,
                    "timestamp": datetime.now().isoformat()
                })
                
                # Update UI
                self.root.after(0, lambda: self.handle_ai_response(response))
                
            except Exception as e:
                logger.error(f"Error generating response: {e}")
                self.root.after(0, lambda: self.handle_error(str(e)))
        
        # Start background thread
        threading.Thread(target=process_response, daemon=True).start()
    
    def handle_ai_response(self, ai_response):
        """Handle AI response in main thread"""
        # Process thinking tags if needed
        if not self.show_thinking.get():
            ai_response = re.sub(r'<think>.*?</think>', '', ai_response, flags=re.DOTALL)
            ai_response = ai_response.strip()
        
        self.add_message("AI", ai_response, "ai")
        
        # Log AI response to file
        self.append_to_chat_log("Companion AI", ai_response)
        
        # Speak if TTS enabled
        if self.tts_enabled.get():
            tts_manager.speak_text(ai_response, blocking=False)
        
        # Re-enable send button
        self.send_btn.config(state=tk.NORMAL, text="↗")
    
    def handle_error(self, error_message):
        """Handle errors"""
        self.add_message("System", f"Error: {error_message}", "system")
        self.send_btn.config(state=tk.NORMAL, text="↗")
    
    # Quick action methods
    
    def review_memory(self):
        """Open detailed memory viewer window"""
        self.open_memory_viewer()
    

    
    def get_insights(self):
        """Get insights from memory"""
        insights = db.get_latest_insights(5)
        if insights:
            insight_text = "💡 Recent Insights:\n\n"
            for insight in insights:
                insight_text += f"• {insight}\n"
        else:
            insight_text = "💡 No insights available yet. Have more conversations to build insights!"
        
        self.add_message("System", insight_text, "system")
    
    def summarize_chat(self):
        """Summarize current chat session"""
        if self.conversation_log:
            summary_text = f"📝 Chat Summary:\n\n"
            summary_text += f"Exchanges: {len(self.conversation_log)}\n"
            summary_text += f"Topics discussed: Various\n"
            summary_text += f"Session active since startup"
        else:
            summary_text = "📝 No conversation to summarize yet!"
        
        self.add_message("System", summary_text, "system")
    
    def voice_settings(self):
        """Show voice settings"""
        voices = tts_manager.get_available_voices()
        current = tts_manager.current_voice
        status = "🔊 Enabled" if tts_manager.is_enabled else "🔇 Disabled"
        
        voice_text = f"🎤 Voice Settings:\n\n"
        voice_text += f"Status: {status}\n"
        voice_text += f"Current voice: {current}\n"
        voice_text += f"Available voices: {len(voices)}"
        
        self.add_message("System", voice_text, "system")
    
    def open_memory_viewer(self):
        """Open detailed memory viewer window"""
        memory_window = tk.Toplevel(self.root)
        memory_window.title("Memory Viewer")
        memory_window.geometry("800x600")
        memory_window.configure(bg=self.colors['bg_primary'])
        
        # Create notebook for tabs
        notebook = ttk.Notebook(memory_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Configure notebook style
        style = ttk.Style()
        style.configure('TNotebook', background=self.colors['bg_primary'])
        style.configure('TNotebook.Tab', background=self.colors['bg_secondary'], foreground=self.colors['text_primary'])
        
        # Profile Facts Tab
        profile_frame = tk.Frame(notebook, bg=self.colors['bg_primary'])
        notebook.add(profile_frame, text="Profile Facts")
        
        profile_text = scrolledtext.ScrolledText(
            profile_frame,
            wrap=tk.WORD,
            font=('Segoe UI', 10),
            bg=self.colors['bg_tertiary'],
            fg=self.colors['text_primary'],
            state=tk.DISABLED,
            relief='flat',
            bd=0,
            padx=15,
            pady=15
        )
        profile_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Summaries Tab
        summaries_frame = tk.Frame(notebook, bg=self.colors['bg_primary'])
        notebook.add(summaries_frame, text="Summaries")
        
        summaries_text = scrolledtext.ScrolledText(
            summaries_frame,
            wrap=tk.WORD,
            font=('Segoe UI', 10),
            bg=self.colors['bg_tertiary'],
            fg=self.colors['text_primary'],
            state=tk.DISABLED,
            relief='flat',
            bd=0,
            padx=15,
            pady=15
        )
        summaries_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Insights Tab
        insights_frame = tk.Frame(notebook, bg=self.colors['bg_primary'])
        notebook.add(insights_frame, text="Insights")
        
        insights_text = scrolledtext.ScrolledText(
            insights_frame,
            wrap=tk.WORD,
            font=('Segoe UI', 10),
            bg=self.colors['bg_tertiary'],
            fg=self.colors['text_primary'],
            state=tk.DISABLED,
            relief='flat',
            bd=0,
            padx=15,
            pady=15
        )
        insights_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Load and display memory data
        self.load_memory_data(profile_text, summaries_text, insights_text)
    
    def load_memory_data(self, profile_widget, summaries_widget, insights_widget):
        """Load memory data into the viewer widgets"""
        try:
            # Profile Facts
            profile = db.get_all_profile_facts()
            profile_widget.config(state=tk.NORMAL)
            profile_widget.delete("1.0", tk.END)
            
            if profile:
                profile_widget.insert(tk.END, "👤 PROFILE FACTS\n")
                profile_widget.insert(tk.END, "=" * 40 + "\n\n")
                for key, value in profile.items():
                    readable_key = key.replace('_', ' ').title()
                    profile_widget.insert(tk.END, f"• {readable_key}:\n")
                    profile_widget.insert(tk.END, f"  {value}\n\n")
            else:
                profile_widget.insert(tk.END, "No profile facts stored yet.")
            
            profile_widget.config(state=tk.DISABLED)
            
            # Summaries
            summaries = db.get_latest_summary(10)
            summaries_widget.config(state=tk.NORMAL)
            summaries_widget.delete("1.0", tk.END)
            
            if summaries:
                summaries_widget.insert(tk.END, "📝 CONVERSATION SUMMARIES\n")
                summaries_widget.insert(tk.END, "=" * 40 + "\n\n")
                for i, summary in enumerate(summaries, 1):
                    summary_text = summary.get('summary_text', 'No summary available')
                    relevance = summary.get('relevance_score', 'N/A')
                    summaries_widget.insert(tk.END, f"{i}. Summary (Relevance: {relevance}):\n")
                    summaries_widget.insert(tk.END, f"{summary_text}\n\n")
            else:
                summaries_widget.insert(tk.END, "No summaries stored yet.")
            
            summaries_widget.config(state=tk.DISABLED)
            
            # Insights
            insights = db.get_latest_insights(10)
            insights_widget.config(state=tk.NORMAL)
            insights_widget.delete("1.0", tk.END)
            
            if insights:
                insights_widget.insert(tk.END, "💡 INSIGHTS\n")
                insights_widget.insert(tk.END, "=" * 40 + "\n\n")
                for i, insight in enumerate(insights, 1):
                    insights_widget.insert(tk.END, f"{i}. {insight}\n\n")
            else:
                insights_widget.insert(tk.END, "No insights stored yet.")
            
            insights_widget.config(state=tk.DISABLED)
            
        except Exception as e:
            logger.error(f"Error loading memory data: {e}")
    
    def export_memory(self):
        """Export memory to text file"""
        try:
            from datetime import datetime
            import os
            
            # Create exports directory if it doesn't exist
            if not os.path.exists("exports"):
                os.makedirs("exports")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"exports/memory_export_{timestamp}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("COMPANION AI MEMORY EXPORT\n")
                f.write("=" * 50 + "\n")
                f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                # Profile Facts
                profile = db.get_all_profile_facts()
                f.write("PROFILE FACTS:\n")
                f.write("-" * 30 + "\n")
                for key, value in profile.items():
                    readable_key = key.replace('_', ' ').title()
                    f.write(f"• {readable_key}: {value}\n")
                f.write("\n")
                
                # Summaries
                summaries = db.get_latest_summary(10)
                f.write("CONVERSATION SUMMARIES:\n")
                f.write("-" * 30 + "\n")
                for i, summary in enumerate(summaries, 1):
                    summary_text = summary.get('summary_text', 'No summary available')
                    relevance = summary.get('relevance_score', 'N/A')
                    f.write(f"{i}. Summary (Relevance: {relevance}):\n")
                    f.write(f"   {summary_text}\n\n")
                
                # Insights
                insights = db.get_latest_insights(10)
                f.write("INSIGHTS:\n")
                f.write("-" * 30 + "\n")
                for i, insight in enumerate(insights, 1):
                    f.write(f"{i}. {insight}\n\n")
            
            self.add_message("System", f"✅ Memory exported to: {filename}", "system")
            
        except Exception as e:
            self.add_message("System", f"❌ Failed to export memory: {e}", "system")
            logger.error(f"Memory export failed: {e}")
    
    def clear_memory(self):
        """Clear memory with confirmation"""
        result = messagebox.askyesno(
            "Clear Memory", 
            "Are you sure you want to clear all memory? This cannot be undone."
        )
        if result:
            try:
                # Clear all memory from database
                db.clear_all_memory()
                self.add_message("System", "🧹 Memory cleared successfully!", "system")
                logger.info("All memory cleared by user")
            except Exception as e:
                self.add_message("System", f"❌ Failed to clear memory: {e}", "system")
                logger.error(f"Memory clearing failed: {e}")
    
    def toggle_voice(self):
        """Toggle voice/TTS"""
        self.tts_enabled.set(not self.tts_enabled.get())
        if self.tts_enabled.get():
            tts_manager.is_enabled = True
            self.voice_btn.configure(fg=self.colors['accent_green'])
            self.add_message("System", "Voice enabled", "system")
        else:
            tts_manager.is_enabled = False
            self.voice_btn.configure(fg=self.colors['text_secondary'])
            self.add_message("System", "Voice disabled", "system")
    
    def change_voice(self, selection):
        """Change TTS voice based on dropdown selection"""
        voice_mapping = {
            "Phoebe Dragon HD": "en-US-Phoebe:DragonHDLatestNeural",
            "Ava Dragon HD": "en-US-Ava:DragonHDLatestNeural"
        }
        
        voice_name = voice_mapping.get(selection)
        if voice_name and tts_manager.set_voice(voice_name):
            self.add_message("System", f"Voice changed to {selection}", "system")
            # Test the new voice
            if tts_manager.is_enabled:
                tts_manager.speak_text(f"Hi, this is {selection.split()[0]}", blocking=False)
        else:
            self.add_message("System", f"Failed to change voice to {selection}", "system")
    
    def change_model(self, selection):
        """Change AI model based on dropdown selection"""
        model_mapping = {
            "DeepSeek R1": "deepseek-r1-distill-llama-70b",
            "Llama 70B": "llama-3.3-70b-versatile", 
            # Removed legacy Kimi model mapping; using Groq models only now
        }
        
        model_name = model_mapping.get(selection)
        if model_name:
            # Store the selected model for use in responses
            self.current_model = model_name
            self.add_message("System", f"Model changed to {selection}", "system")
        else:
            self.add_message("System", f"Failed to change model to {selection}", "system")
    
    def change_persona(self, selection):
        """Change AI persona based on dropdown selection"""
        if selection in ["Aether", "Lilith"]:
            self.current_persona = selection
            self.add_message("System", f"Persona changed to {selection}", "system")
        else:
            self.add_message("System", f"Failed to change persona to {selection}", "system")
    
    def on_enter_key(self, event):
        """Handle Enter key press in message entry"""
        # Check if Shift is held down
        if event.state & 0x1:  # Shift key is pressed
            return  # Allow normal newline behavior
        else:
            # Send message on Enter (without Shift)
            self.send_message()
            return "break"  # Prevent default behavior
    
    def clear_chat(self):
        """Clear the chat display"""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete("1.0", tk.END)
        self.chat_display.config(state=tk.DISABLED)
        
        # Clear conversation log
        self.conversation_log = []
        
        # Show welcome message again
        self.show_welcome_message()
        
        self.add_message("System", "💬 Chat cleared! Starting fresh.", "system")
    
    def on_window_resize(self, event):
        """Handle window resize for responsive design"""
        # Only handle root window resize events
        if event.widget != self.root:
            return
            
        window_width = self.root.winfo_width()
        
        # Only update if width changed significantly
        if abs(window_width - self.current_window_width) < 50:
            return
            
        self.current_window_width = window_width
        
        # Adjust header font sizes for smaller windows
        if window_width < 700:
            self.title_label.configure(font=('Segoe UI', 18, 'normal'))
            self.subtitle_label.configure(font=('Segoe UI', 10))
        else:
            self.title_label.configure(font=('Segoe UI', 24, 'normal'))
            self.subtitle_label.configure(font=('Segoe UI', 12))
        
        # Adjust button layout based on window width
        if hasattr(self, 'action_buttons') and self.action_buttons:
            if window_width < 700:
                # Stack buttons vertically for narrow windows
                self.adjust_buttons_for_narrow_window()
            else:
                # Use normal horizontal layout for wider windows
                self.adjust_buttons_for_wide_window()
    
    def adjust_buttons_for_narrow_window(self):
        """Adjust button layout for narrow windows"""
        try:
            # Clear existing layout
            for row_frame in self.row_frames:
                for widget in row_frame.winfo_children():
                    widget.pack_forget()
            
            # Repack all buttons in a single column with smaller text
            all_buttons_data = []
            for row in self.actions_data:
                all_buttons_data.extend(row)
            
            # Use first row frame for all buttons
            if self.row_frames:
                main_frame = self.row_frames[0]
                
                for i, (text, cmd) in enumerate(all_buttons_data):
                    if i < len(self.action_buttons[0]) + len(self.action_buttons[1]):
                        # Get button from either row
                        if i < len(self.action_buttons[0]):
                            btn = self.action_buttons[0][i]
                        else:
                            btn = self.action_buttons[1][i - len(self.action_buttons[0])]
                        
                        # Reparent to main frame and adjust styling
                        btn.configure(font=('Segoe UI', 9), padx=10, pady=6)
                        btn.pack(side=tk.TOP, fill=tk.X, pady=2, padx=5)
        except Exception as e:
            logger.error(f"Error adjusting buttons for narrow window: {e}")
    
    def adjust_buttons_for_wide_window(self):
        """Adjust button layout for wide windows"""
        try:
            # Clear existing layout
            for row_frame in self.row_frames:
                for widget in row_frame.winfo_children():
                    widget.pack_forget()
            
            # Restore original two-row layout
            for row_idx, (row_buttons, row_data) in enumerate(zip(self.action_buttons, self.actions_data)):
                row_frame = self.row_frames[row_idx]
                
                for btn, (text, cmd) in zip(row_buttons, row_data):
                    # Restore original styling
                    btn.configure(font=('Segoe UI', 10), padx=15, pady=8)
                    btn.pack(side=tk.LEFT, padx=(0, 10))
        except Exception as e:
            logger.error(f"Error adjusting buttons for wide window: {e}")
    
    def on_closing(self):
        """Handle window closing"""
        if self.conversation_log:
            logger.info(f"Processing session memory for {len(self.conversation_log)} exchanges")
            # Process session memory with Memory AI
            self._process_session_memory()
            # Create session log file for review
            self._create_session_log()
        
        # Finalize chat log
        try:
            session_end = datetime.now()
            duration = session_end - self.session_start
            with open(self.chat_log_file, 'a', encoding='utf-8') as f:
                f.write("\n" + "=" * 80 + "\n")
                f.write(f"Session Ended: {session_end.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Duration: {duration}\n")
                f.write(f"Total Exchanges: {len(self.conversation_log)}\n")
                f.write("=" * 80 + "\n")
            logger.info(f"Chat log finalized: {self.chat_log_file}")
        except Exception as e:
            logger.error(f"Failed to finalize chat log: {e}")
        
        logger.info("Companion AI session ended")
        self.root.destroy()
    
    def _create_session_log(self):
        """Create a session log file with the conversation and schedule cleanup"""
        try:
            from datetime import datetime
            import threading
            import os
            import time
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"session_log_{timestamp}.txt"
            
            with open(log_filename, "w", encoding="utf-8") as f:
                f.write(f"Companion AI Session Log\n")
                f.write(f"Session Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total Exchanges: {len(self.conversation_log)}\n")
                f.write("=" * 50 + "\n\n")
                
                for i, exchange in enumerate(self.conversation_log, 1):
                    f.write(f"Exchange {i}:\n")
                    f.write(f"User: {exchange['user']}\n")
                    f.write(f"AI: {exchange['ai']}\n")
                    f.write(f"Time: {exchange['timestamp']}\n")
                    f.write("-" * 30 + "\n\n")
            
            logger.info(f"Session log saved as: {log_filename}")
            
            # Clean up old session logs (keep only the most recent one)
            self._cleanup_old_session_logs(log_filename)
            
        except Exception as e:
            logger.error(f"Failed to create session log: {e}")
    
    def _process_session_memory(self):
        """Process session memory with Memory AI"""
        try:
            from companion_ai import memory_ai
            
            # Format conversation for analysis
            conversation_text = ""
            for i, exchange in enumerate(self.conversation_log, 1):
                conversation_text += f"Exchange {i}:\n"
                conversation_text += f"User: {exchange['user']}\n"
                conversation_text += f"AI: {exchange['ai']}\n\n"
            
            # Analyze session importance
            importance_score = memory_ai.analyze_conversation_importance(
                conversation_text, "", {}
            )
            
            logger.info(f"Session importance: {importance_score:.2f}")
            
            if importance_score > 0.15:
                # Generate session summary
                summary = memory_ai.generate_smart_summary(
                    conversation_text, "", importance_score
                )
                if summary:
                    db.add_summary(summary, relevance_score=importance_score)
                    logger.info("Session summary stored")
                
                # Extract profile facts
                facts = memory_ai.extract_smart_profile_facts(conversation_text, "")
                if facts:
                    for key, fact_data in facts.items():
                        db.upsert_profile_fact(
                            key,
                            fact_data['value'],
                            confidence=fact_data.get('confidence', 0.5),
                            source='session_analysis',
                            evidence=fact_data.get('evidence'),
                            model_conf_label=fact_data.get('conf_label'),
                            justification=fact_data.get('justification')
                        )
                    logger.info(f"Profile facts stored: {list(facts.keys())}")
                
                # Generate insights
                insight = memory_ai.generate_contextual_insight(
                    conversation_text, "", {}, importance_score
                )
                if insight:
                    category = memory_ai.categorize_insight(insight)
                    db.add_insight(insight, category=category, relevance_score=importance_score)
                    logger.info("Session insight stored")
            else:
                logger.info("Low importance session - minimal storage")
                
        except Exception as e:
            logger.error(f"Session memory processing failed: {e}")
    
    def _cleanup_old_session_logs(self, current_log: str):
        """Keep only the most recent session log, delete older ones"""
        try:
            import glob
            import os
            
            # Find all session log files
            session_logs = glob.glob("session_log_*.txt")
            
            # Remove the current log from the list
            if current_log in session_logs:
                session_logs.remove(current_log)
            
            # Delete all old session logs
            for old_log in session_logs:
                try:
                    os.remove(old_log)
                    logger.info(f"Cleaned up old session log: {old_log}")
                except Exception as e:
                    logger.error(f"Failed to remove {old_log}: {e}")
                    
        except Exception as e:
            logger.error(f"Session log cleanup failed: {e}")

def main():
    """Main function to run the Copilot-style GUI"""
    root = tk.Tk()
    app = CopilotCompanionGUI(root)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        messagebox.showerror("Error", f"An error occurred: {e}")

if __name__ == "__main__":
    main()