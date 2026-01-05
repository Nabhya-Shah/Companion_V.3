#!/usr/bin/env python3
"""
Azure TTS Manager - Handles text-to-speech functionality
"""

import os
import logging
import threading
from typing import Optional

# Conditional import - Azure SDK is optional
try:
    import azure.cognitiveservices.speech as speechsdk
    AZURE_AVAILABLE = True
except ImportError:
    speechsdk = None
    AZURE_AVAILABLE = False

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class AzureTTSManager:
    """Manages Azure Text-to-Speech functionality"""
    
    def __init__(self):
        self.speech_key = os.getenv("AZURE_SPEECH_KEY")
        self.speech_region = os.getenv("AZURE_SPEECH_REGION")
        self.speech_config = None
        self.synthesizer = None
        self.is_enabled = False
        self.current_synthesis = None  # Track current synthesis for interruption
        
        # Default settings (initialized even if Azure is not available)
        self.current_voice = "en-US-PhoebeMultilingualNeural"  # Default high-quality
        self.speech_rate = "+5%"   # Just slightly faster, not rushed
        self.speech_pitch = "+0%"  # No pitch changes - keep natural
        self.speech_volume = "+0%" # Normal volume

        # Check if Azure SDK is available
        if not AZURE_AVAILABLE:
            logger.warning("Azure Speech SDK not installed. TTS disabled.")
            return
        
        self._initialize_tts()
    
    def _initialize_tts(self):
        """Initialize Azure TTS service"""
        if not self.speech_key or not self.speech_region:
            logger.warning("Azure Speech credentials not found. TTS disabled.")
            return
        
        try:
            # Create speech config
            self.speech_config = speechsdk.SpeechConfig(
                subscription=self.speech_key, 
                region=self.speech_region
            )
            
            # Set voice
            self.speech_config.speech_synthesis_voice_name = self.current_voice
            
            # Create synthesizer
            self.synthesizer = speechsdk.SpeechSynthesizer(speech_config=self.speech_config)
            
            self.is_enabled = True
            logger.info(f"Azure TTS initialized successfully with voice: {self.current_voice}")
            
        except Exception as e:
            logger.error(f"Azure TTS initialization failed: {e}")
            self.is_enabled = False
    
    def speak_text(self, text: str, blocking: bool = False) -> bool:
        """
        Convert text to speech and play it with SSML for speed/pitch control
        
        Args:
            text: Text to speak
            blocking: If True, wait for speech to complete
            
        Returns:
            True if speech started successfully, False otherwise
        """
        if not self.is_enabled or not text.strip():
            return False
        
        try:
            # Clean text for better speech
            clean_text = self._clean_text_for_speech(text)
            
            # Adjust voice parameters based on content mood
            adjusted_ssml = self._create_mood_adjusted_ssml(clean_text)
            
            if blocking:
                # Synchronous speech
                result = self.synthesizer.speak_ssml_async(adjusted_ssml).get()
                if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                    return True
                else:
                    logger.error(f"TTS failed: {result.reason}")
                    if result.reason == speechsdk.ResultReason.Canceled:
                        cancellation = result.cancellation_details
                        logger.error(f"TTS cancellation reason: {cancellation.reason}")
                        if cancellation.error_details:
                            logger.error(f"TTS error details: {cancellation.error_details}")
                    return False
            else:
                # Asynchronous speech
                def speak_async():
                    try:
                        # Store the synthesis task for potential interruption
                        self.current_synthesis = self.synthesizer.speak_ssml_async(adjusted_ssml)
                        result = self.current_synthesis.get()
                        
                        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                            logger.info("TTS completed successfully")
                        else:
                            logger.error(f"TTS failed: {result.reason}")
                            if result.reason == speechsdk.ResultReason.Canceled:
                                cancellation = result.cancellation_details
                                logger.error(f"TTS cancellation reason: {cancellation.reason}")
                                if cancellation.error_details:
                                    logger.error(f"TTS error details: {cancellation.error_details}")
                    except Exception as e:
                        logger.error(f"Async TTS error: {e}")
                    finally:
                        self.current_synthesis = None
                
                threading.Thread(target=speak_async, daemon=True).start()
                return True
                
        except Exception as e:
            logger.error(f"TTS speak_text failed: {e}")
            return False
    
    def stop_current_speech(self):
        """Stop any currently playing speech"""
        try:
            if self.current_synthesis:
                # Cancel the current synthesis
                self.current_synthesis.cancel()
                self.current_synthesis = None
                logger.info("Current TTS speech stopped")
        except Exception as e:
            logger.error(f"Error stopping TTS: {e}")
    
    def _create_ssml(self, text: str) -> str:
        """Create SSML markup with voice, rate, pitch, and volume settings"""
        ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
    <voice name="{self.current_voice}">
        <prosody rate="{self.speech_rate}" pitch="{self.speech_pitch}" volume="{self.speech_volume}">
            {text}
        </prosody>
    </voice>
</speak>"""
        return ssml
    
    def _create_mood_adjusted_ssml(self, text: str) -> str:
        """Create SSML with mood-based adjustments for Neuro-sama personality"""
        import re
        
        # Detect mood/tone from text content
        excited_patterns = ['!', 'wow', 'amazing', 'awesome', 'omg', 'yay', 'haha', 'lol']
        serious_patterns = ['alright enough', 'i need this', 'be serious', 'focus', 'important']
        playful_patterns = ['hehe', 'tease', 'silly', 'fun', 'play', 'joke']
        dramatic_patterns = ['how dare', 'unbelievable', 'absolutely', 'totally']
        
        text_lower = text.lower()
        
        # Adjust voice parameters based on detected mood
        rate = self.speech_rate
        pitch = self.speech_pitch
        volume = self.speech_volume
        
        if any(pattern in text_lower for pattern in serious_patterns):
            # Serious mode: slightly slower, natural pitch, more controlled
            rate = "-3%"
            pitch = "+0%"
            volume = "+3%"
        elif any(pattern in text_lower for pattern in excited_patterns):
            # Excited mode: slightly faster, tiny pitch increase
            rate = "+8%"
            pitch = "+5%"
            volume = "+5%"
        elif any(pattern in text_lower for pattern in dramatic_patterns):
            # Dramatic mode: moderate pace with slight emphasis
            rate = "+5%"
            pitch = "+8%"
            volume = "+8%"
        elif any(pattern in text_lower for pattern in playful_patterns):
            # Playful mode: natural pace with slight bounce
            rate = "+3%"
            pitch = "+3%"
            volume = "+3%"
        
        # Create SSML with mood adjustments
        ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
    <voice name="{self.current_voice}">
        <prosody rate="{rate}" pitch="{pitch}" volume="{volume}">
            {text}
        </prosody>
    </voice>
</speak>"""
        return ssml
    
    def _clean_text_for_speech(self, text: str) -> str:
        """Clean text to make it more suitable for speech synthesis with personality"""
        import re
        
        # Remove thinking tags if present
        clean_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        # Remove excessive whitespace
        clean_text = ' '.join(clean_text.split())
        
        # Enhanced replacements for better speech flow and personality
        replacements = {
            '...': '<break time="0.5s"/>',  # Add natural pauses for dramatic effect
            '--': '<break time="0.3s"/>',   # Shorter pause for dashes
            '!!': '!',                      # Reduce excessive exclamation
            '???': '?',                     # Reduce excessive questions
            '  ': ' ',                      # Clean double spaces
            'lol': '<emphasis level="moderate">lol</emphasis>',  # Emphasize laughter
            'haha': '<emphasis level="moderate">haha</emphasis>',
            'omg': '<emphasis level="strong">oh my god</emphasis>',
            'btw': 'by the way',
            'tbh': 'to be honest',
            'ngl': 'not gonna lie',
        }
        
        for old, new in replacements.items():
            clean_text = clean_text.replace(old, new)
        
        # Add natural breathing pauses for longer sentences
        sentences = clean_text.split('. ')
        if len(sentences) > 2:
            clean_text = '. <break time="0.4s"/>'.join(sentences)
        
        return clean_text.strip()
    
    def set_voice(self, voice_name: str) -> bool:
        """Change the TTS voice"""
        try:
            self.current_voice = voice_name
            
            # Azure logic: Only update Azure synthesizer if not a Groq voice logic (handled in speak_text_groq)
            # Actually, standard Azure sets voice on the config.
            if hasattr(self, 'speech_config') and self.speech_config:
                self.speech_config.speech_synthesis_voice_name = voice_name
                self.synthesizer = speechsdk.SpeechSynthesizer(speech_config=self.speech_config)
            
            logger.info(f"Voice changed to: {voice_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to change voice: {e}")
            return False

    def speak_text_groq(self, text: str, blocking: bool = False):
        """Speak text using Groq's Orpheus model (High Speed)"""
        import requests
        import os
        import io
        import sounddevice as sd
        import soundfile as sf
        
        try:
            api_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_TOOL_API_KEY")
            if not api_key:
                logger.error("GROQ_API_KEY not found for TTS")
                return False

            # Map Azure voices to Groq personas if needed, or default to Hannah
            groq_voice = "Hannah" 
            if "male" in self.current_voice.lower() or "guy" in self.current_voice.lower() or "davis" in self.current_voice.lower():
                groq_voice = "Troy"
            
            url = "https://api.groq.com/openai/v1/audio/speech"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "canopylabs/orpheus-v1-english",
                "input": text,
                "voice": groq_voice
            }
            
            # Execute request
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code != 200:
                logger.error(f"Groq TTS Error ({response.status_code}): {response.text}")
                return False
                
            # Play audio
            audio_data = io.BytesIO(response.content)
            data, samplerate = sf.read(audio_data)
            
            if blocking:
                sd.play(data, samplerate)
                sd.wait()
            else:
                sd.play(data, samplerate)
                
            logger.info("Groq TTS (Orpheus) playback started")
            return True
            
        except Exception as e:
            logger.error(f"Groq TTS failed: {e}")
            return False

    def speak_text(self, text: str, blocking: bool = False):
        """
        Speak the provided text using the configured TTS provider.
        """
        if not self.is_enabled:
            return

        # Check for Groq provider flag
        if getattr(self, 'provider', 'azure') == 'groq':
            # Clean text but keep [brackets] for Orpheus
            # _clean_text_for_speech removes logic tags but we rely on its basic cleanup
            clean_text = self._clean_text_for_speech(text)
            self.current_synthesis = "groq"
            success = self.speak_text_groq(clean_text, blocking)
            self.current_synthesis = None
            
            if success:
                return
            
            logger.warning("Groq TTS failed or declined, falling back to Azure")
            # Fall through to Azure implementation below

        # --- Azure Implementation ---
        if not self.synthesizer:
            logger.warning("TTS enabled but synthesizer not initialized")
            return

        try:
            # Azure specific text cleaning
            text_to_speak = self._clean_text_for_speech(text)
            
            if not text_to_speak:
                return

            ssml = self._create_mood_adjusted_ssml(text_to_speak)
            
            if blocking:
                result = self.synthesizer.speak_ssml_async(ssml).get()
            else:
                result = self.synthesizer.start_speaking_ssml_async(ssml).get()
                self.current_synthesis = result
                
        except Exception as e:
            logger.error(f"TTS Error: {e}")
    
    def set_speech_rate(self, rate: str) -> bool:
        """Set speech rate (e.g., '-20%', '0%', '+20%')"""
        try:
            self.speech_rate = rate
            # Note: Rate changes require SSML for full control
            logger.info(f"Speech rate set to: {rate}")
            return True
        except Exception as e:
            logger.error(f"Failed to set speech rate: {e}")
            return False
    
    def set_speech_pitch(self, pitch: str) -> bool:
        """Set speech pitch (e.g., '-10%', '0%', '+10%')"""
        try:
            self.speech_pitch = pitch
            logger.info(f"Speech pitch set to: {pitch}")
            return True
        except Exception as e:
            logger.error(f"Failed to set speech pitch: {e}")
            return False
    
    def get_available_voices(self) -> list:
        """Get list of available voices optimized for companion AI personality"""
        return [
            # High Quality Neural (Requires West Europe / East US)
            "en-US-Phoebe:DragonHDLatestNeural",
            "en-US-Ava:DragonHDLatestNeural",
            "en-US-Andrew2:DragonHDLatestNeural",
            
            # Standard Multilingual (Works everywhere)
            "en-US-PhoebeMultilingualNeural",
            "en-US-AvaMultilingualNeural",
            "en-US-AndrewMultilingualNeural",
            "en-US-BrianMultilingualNeural",
            "en-US-EmmaMultilingualNeural",
            
            # Standard Neural
            "en-US-AnaNeural",
            "en-US-AriaNeural",
            "en-US-JennyNeural",
            "en-US-GuyNeural",
            "en-US-DavisNeural",
            "en-US-ChristopherNeural",
            "en-US-NancyMultilingualNeural",
            "en-US-SerenaMultilingualNeural",
        ]
    
    def test_tts(self) -> bool:
        """Test TTS functionality"""
        if not self.is_enabled:
            logger.warning("TTS not enabled - check Azure credentials")
            return False
        
        test_text = "Hello! Azure Text-to-Speech is working correctly."
        return self.speak_text(test_text, blocking=True)
    
    def stop_speech(self):
        """Stop current speech synthesis"""
        try:
            import sounddevice as sd
            # Stop Groq audio (sounddevice)
            sd.stop()
            
            # Stop Azure audio
            if self.synthesizer:
                try:
                    self.synthesizer.stop_speaking_async()
                except:
                    pass
                    
            logger.info("Speech stopped")
        except Exception as e:
            logger.error(f"Failed to stop speech: {e}")
    
    def toggle_enabled(self) -> bool:
        """Toggle TTS on/off"""
        if self.speech_key and self.speech_region:
            self.is_enabled = not self.is_enabled
            logger.info(f"TTS {'enabled' if self.is_enabled else 'disabled'}")
        else:
            logger.warning("Cannot enable TTS - missing Azure credentials")
            self.is_enabled = False
        
        return self.is_enabled
    
    def get_status(self) -> dict:
        """Get current TTS status and settings"""
        return {
            "enabled": self.is_enabled,
            "voice": self.current_voice,
            "rate": self.speech_rate,
            "pitch": self.speech_pitch,
            "has_credentials": bool(self.speech_key and self.speech_region)
        }

# Global TTS manager instance
tts_manager = AzureTTSManager()