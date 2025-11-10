"""Analyze token usage in different parts of the system prompt."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from companion_ai.core.context_builder import build_system_prompt_with_meta

# Rough token estimate (1 token ≈ 4 characters for English text)
def estimate_tokens(text: str) -> int:
    """Rough GPT token estimate: ~1 token per 4 chars"""
    return len(text) // 4

def analyze_prompt():
    print("=" * 70)
    print("TOKEN USAGE ANALYSIS")
    print("=" * 70)
    
    # Test with a typical message
    test_message = "How are you doing?"
    test_conversation = "User: Hey\nAI: Hey! What's up?\nUser: Not much"
    
    result = build_system_prompt_with_meta(test_message, test_conversation)
    system_prompt = result['system_prompt']
    
    # Split into sections
    sections = {}
    
    # Extract each section
    lines = system_prompt.split('\n')
    current_section = "HEADER"
    current_text = []
    
    for line in lines:
        if line.startswith('PERSONALITY:'):
            if current_text:
                sections[current_section] = '\n'.join(current_text)
            current_section = "PERSONALITY"
            current_text = [line]
        elif line.startswith('CORE RULES:'):
            if current_text:
                sections[current_section] = '\n'.join(current_text)
            current_section = "CORE_RULES"
            current_text = [line]
        elif line.startswith('CONVERSATION FLOW'):
            if current_text:
                sections[current_section] = '\n'.join(current_text)
            current_section = "CONVERSATION_FLOW"
            current_text = [line]
        elif line.startswith('ENGAGEMENT:'):
            if current_text:
                sections[current_section] = '\n'.join(current_text)
            current_section = "ENGAGEMENT"
            current_text = [line]
        elif line.startswith('MEMORY USAGE'):
            if current_text:
                sections[current_section] = '\n'.join(current_text)
            current_section = "MEMORY_USAGE"
            current_text = [line]
        elif line.startswith('CURRENT MODE:'):
            if current_text:
                sections[current_section] = '\n'.join(current_text)
            current_section = "MODE_VIBE"
            current_text = [line]
        elif line.startswith('CONTEXT ('):
            if current_text:
                sections[current_section] = '\n'.join(current_text)
            current_section = "MEMORY_CONTEXT"
            current_text = [line]
        elif line.startswith('RECENT CONVERSATION'):
            if current_text:
                sections[current_section] = '\n'.join(current_text)
            current_section = "CONVERSATION_HISTORY"
            current_text = [line]
        else:
            current_text.append(line)
    
    if current_text:
        sections[current_section] = '\n'.join(current_text)
    
    # Analyze each section
    print("\n📊 BREAKDOWN BY SECTION:\n")
    total_tokens = 0
    section_data = []
    
    for section, text in sections.items():
        tokens = estimate_tokens(text)
        total_tokens += tokens
        section_data.append((section, tokens, len(text)))
    
    # Sort by token count
    section_data.sort(key=lambda x: x[1], reverse=True)
    
    for section, tokens, chars in section_data:
        percentage = (tokens / total_tokens * 100) if total_tokens > 0 else 0
        print(f"  {section:25} {tokens:5} tokens ({percentage:5.1f}%) | {chars:6} chars")
    
    print(f"\n{'TOTAL':25} {total_tokens:5} tokens | {len(system_prompt):6} chars")
    print("=" * 70)
    
    # Show full prompt for reference
    print("\n📄 FULL SYSTEM PROMPT:")
    print("-" * 70)
    print(system_prompt)
    print("-" * 70)
    
    # Recommendations
    print("\n💡 TOP OPTIMIZATION TARGETS (by token usage):\n")
    for i, (section, tokens, chars) in enumerate(section_data[:5], 1):
        percentage = (tokens / total_tokens * 100)
        print(f"{i}. {section}: {tokens} tokens ({percentage:.1f}%)")
        
        # Specific recommendations
        if section == "CONVERSATION_FLOW":
            print("   → This is very verbose. Could condense repetitive rules.")
        elif section == "MEMORY_USAGE":
            print("   → Long instruction block. Could simplify with examples instead of rules.")
        elif section == "CONVERSATION_HISTORY":
            print("   → This grows with conversation length. Consider limiting to last N exchanges.")
        elif section == "ENGAGEMENT":
            print("   → Overlaps with CONVERSATION_FLOW. Could merge or shorten.")
        elif section == "CORE_RULES":
            print("   → Essential but could be more concise.")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    analyze_prompt()
