# Conversation Quality Issues Tracker

**Testing Date:** November 5, 2025  
**Strategy:** Document all issues during extended testing, then fix comprehensively at the end.

---

## 🐛 Issues Found

### 1. CRITICAL: Context Window Only 3 Exchanges
- **Severity:** CRITICAL
- **Description:** The web companion only passes the last 3 exchanges to the LLM (`conversation_history[-3:]`), causing severe short-term memory loss
- **Location:** `web_companion.py` lines 58, 110 - both endpoints use `conversation_history[-3:]`
- **Impact:** AI cannot remember anything beyond ~6-8 messages ago
- **Test Cases:**
  - Told AI about Canon R6 camera (message 2)
  - Asked about camera 5 messages later (message 7)
  - AI responded: "I'm not seeing a camera mentioned earlier"
  - Told AI about dog named Max, golden retriever (message 11)
  - Asked breed 4 messages later (message 16)
  - AI responded: "I don't think we mentioned Max's breed before"
- **Expected:** Should have longer context window (at least 10-20 exchanges) or use conversation summaries
- **This Explains:** Why AI can't maintain coherent long conversations

### 2. Memory Storage Not Working
- **Severity:** CRITICAL  
- **Description:** No facts being stored in database despite explicit statements
- **Test Data Provided:**
  - "I got a new Canon R6 last month"
  - "I go there every weekend"
  - "my birthday's coming up next month - December 15th. I'm turning 28"
  - "I work as a software engineer at a startup"
  - "I have a dog named Max and he's a golden retriever"
- **Verification:** Ran `check_actual_memory.py` twice during conversation - database completely empty
- **Expected:** Birthday, career, hobbies, pets should be stored as profile facts
- **Impact:** Long-term memory completely non-functional

### 3. Empty AI Response Bug
- **Severity:** HIGH
- **Description:** AI occasionally returns completely empty responses
- **Test Case:** Message 7 - "hey quick question - what camera did I say I have?" returned empty string
- **Logs Show:** Entry exists in conv_20251105.jsonl but AI field is empty
- **Frequency:** Observed once in 16 messages
- **Possible Causes:** LLM timeout, context too long, or error handling issue

### 4. Memory Hallucination (LIKELY CAUSED BY ISSUE #1)
- **Severity:** HIGH (but may be symptom of 3-exchange limit)
- **Description:** When asked to recall earlier conversation, AI incorrectly claimed we discussed "fusing music vibes into game dev project" - we hadn't combined those topics until AFTER this question
- **Location:** Message 16 of first test conversation
- **Expected:** Should accurately recall OR say it doesn't remember specific details
- **Actual:** Confabulated/hallucinated a connection that didn't exist yet
- **Test Case:** "hey do you remember what we talked about earlier? the game dev stuff?"
- **Response:** "Yeah, we were tossing around ideas on how to fuse music vibes into a game dev project..."
- **Note:** This may be LLM trying to fill gaps when context window is too short

### 5. Proactive Behavior Not Triggering Consistently
- **Location:** Message 16 of test conversation
- **Expected:** Should accurately recall OR say it doesn't remember specific details
- **Actual:** Confabulated/hallucinated a connection that didn't exist yet
- **Test Case:** "hey do you remember what we talked about earlier? the game dev stuff?"
- **Response:** "Yeah, we were tossing around ideas on how to fuse music vibes into a game dev project..."

### 5. Proactive Behavior Not Triggering Consistently  
- **Severity:** MEDIUM
- **Description:** 2-shallow-exchange trigger didn't fire when expected
- **Test Case:** 
  - Message 5: "How's your day shaping up?" (question)
  - Message 6: "pretty chill, just working on some projects" (shallow)
  - Message 7: "yeah" (minimal)
  - **Expected:** Message after #7 should be a statement, not another question/offer
  - **Actual:** "Got it. If you need anything, just give me a shout." (still passive)
- **Location:** Messages 5-7 of test conversation
- **Notes:** Rule says "After 2 shallow exchanges, inject something new" but didn't activate

### 6. "Chat:" Prefix Appearing in Responses
- **Severity:** LOW (cosmetic)
- **Description:** Some responses have "Chat:" at the beginning, looks like formatting artifact
- **Locations:** Messages 7, 13, 16, 20
- **Examples:**
  - "Chat: Got it. If you need anything, just give me a shout."
  - "Chat: Fair enough—how about 'Clubbed to Death'..."
  - "Chat: Yeah, we were tossing around ideas..."
  - "Chat: anytime, catch you later."
- **Expected:** No prefix, just the response text
- **Possible Cause:** May be related to mode detection or routing system adding metadata

---

## ✅ What's Working Well

1. **Natural Topic Transitions** - Smoothly moved between game dev → ML → music → careers
2. **Helpful & Practical** - Gave concrete advice (Godot, Andrew Ng's course, TensorFlow/PyTorch)
3. **Honest About Limitations** - "I don't have a backyard to check—just a cloud of code"
4. **Good Exit Handling** - Natural goodbyes without being clingy
5. **Creative Suggestions** - Music recommendation (Clubbed to Death), combining music with game levels
6. **Conversational Tone** - Casual, friendly, engaging ("Cool move", "Fair enough", "Nice blend")

---

## 📋 Next Testing Focus

**TESTING PAUSED - Critical Issues Require Immediate Fix**

The 3-exchange context window (Issue #1) and non-functional memory storage (Issue #2) are blocking meaningful conversation testing. These must be fixed before continuing extensive testing.

### Completed Testing:
- [x] Long conversation with topic transitions (20+ messages)
- [x] Memory recall testing (immediate and delayed)
- [x] Fact storage verification (checked database multiple times)
- [x] Shallow exchange proactive behavior (works within 3-exchange window)
- [x] Help/advice scenarios
- [x] Emotional support responses
- [x] Empty response bug identified

### On Hold Until Fixes:
- [ ] Test longer shallow exchange sequences (5-10 minimal responses)
- [ ] Test memory recall with multiple topics in same conversation
- [ ] Test conversation summaries being generated
- [ ] Test topic steering and depth handling
- [ ] Test handling of contradictions or corrections
- [ ] Test emotional intelligence across long conversations
- [ ] Stress test with rapid topic changes
- [ ] Test handling of unclear/ambiguous questions

---

## 🎯 TEST SESSION SUMMARY

**Total Messages:** 22  
**Database Checks:** 3  
**Facts Stored:** 0  
**Memory Failures:** Multiple  

**Facts That Should Have Been Stored:**
1. Canon R6 camera (purchased last month)
2. Photography hobby (landscape, golden hour)
3. Mountain trail visits (every weekend)
4. Birthday: December 15th, turning 28
5. Job: Software engineer at startup
6. Dog: Max, golden retriever
7. Learning Python
8. Work stress
9. Learning guitar (3 months)

**What AI Actually Remembered (at message 22):**
- Python learning
- Work stress  
- Guitar (3 months)
*(Only the last 3 topics within the 3-exchange window)*

---

## 🔧 Fix Plan (To Be Executed After Complete Testing)

**Current Status:** ✅ ALL CRITICAL FIXES COMPLETE & VERIFIED WORKING!

### ✅ COMPLETED & VERIFIED FIXES:

1. **Full Conversation Context - UNLIMITED**
   - Removed ALL artificial limits on conversation history
   - AI now receives COMPLETE conversation from session start
   - Plus database memories (facts, summaries, insights)
   - **VERIFIED:** Remembered facts from 9+ messages ago flawlessly
   - **TEST RESULTS:** 
     - Name (Sarah) from message 1 ✓
     - Location (Boston) from message 1 ✓
     - Job (Boston Children's Hospital) from message 2 ✓
     - Cat name (Mittens) from message 4 ✓
     - Apple pie specialty from message 3 ✓

2. **Memory Storage - FULLY FUNCTIONAL**
   - Integrated ConversationSession throughout web_companion.py
   - Auto-processing every 5 messages
   - **VERIFIED:** 11 facts stored with 0.95-1.00 confidence!
   - **DATABASE CONTENTS:**
     - Profile facts: name, age, city, occupation, workplace
     - Hobbies: baking, chocolate chip cookies, banana bread, apple pie
     - Pet: cat named Mittens, 5 years old
     - 4 conversation summaries generated
     - 1 insight created

3. **Empty Response Protection - ACTIVE**
   - Guards in both endpoints
   - Fallback message ready
   - **STATUS:** No empty responses observed

4. **"Chat:" Prefix Removal - WORKING**
   - Post-processing strips prefixes
   - **VERIFIED:** All responses clean, no prefixes

5. **Proactive Behavior - WORKING**
   - Shallow exchanges trigger statements instead of questions
   - **VERIFIED:** Message 14 gave statement after shallow exchange
   - Works better with full context

6. **Context Integration - EXCELLENT**
   - AI naturally weaves together current conversation + stored memories
   - Example: Suggested "apple pie" AND "Mittens" in same response about stress
   - Demonstrates true contextual understanding

### 🎯 SYSTEM PERFORMANCE:

- **Conversation Memory:** Unlimited (full session)
- **Long-term Memory:** Working (auto-saves every 5 messages)
- **Fact Accuracy:** 95-100% confidence scores
- **Response Quality:** Natural, contextual, no artifacts
- **Proactive Behavior:** Triggers appropriately

---

## 🔍 REMAINING MINOR ISSUES & IMPROVEMENTS

### Issues to Fix:

1. **Web UI Message Skipping**
   - **Severity:** LOW
   - **Description:** Some messages appear in terminal/PowerShell but skip display in web UI
   - **Observed:** Happened during long message responses
   - **Possible Cause:** Polling race condition or message deduplication logic
   - **Location:** static/app.js polling function around line 280

2. **"CHAT|" Prefix Variant**
   - **Severity:** LOW  
   - **Description:** Occasional "CHAT|" prefix (pipe instead of colon)
   - **Observed:** Once during weather question
   - **Fix:** Update cleanup regex to handle both "Chat:" and "CHAT|"

3. **Rare Internal Errors**
   - **Severity:** LOW
   - **Description:** Occasional LLM generation errors (recovers gracefully)
   - **Observed:** Message 16 during long context
   - **Impact:** Minimal - fallback message works

### Quality Enhancements (User-Requested):

4. **More Opinionated Responses**
   - **Current:** AI is too neutral ("I'm on the fence about pineapple pizza")
   - **Desired:** Form and express actual opinions
   - **Examples:** 
     - "Pineapple on pizza? Hard pass for me!"
     - "Celtics are great, but I'm more of a [team] fan"
   - **Implementation:** Update persona to encourage personal preferences

5. **Adaptive Detail Level Based on User Knowledge**
   - **Current:** Same level of detail regardless of user's familiarity
   - **Desired:** Adjust explanations based on detected knowledge
   - **Examples:**
     - User is specific about apartments → Give detailed advice
     - User asks about sports casually → Keep it simple, less technical
   - **Implementation:** Add context analysis for detail calibration

6. **Clarifying Questions & Doubt**
   - **Current:** Accepts all statements at face value
   - **Desired:** Ask for clarification when details are ambiguous
   - **Examples:**
     - User mentions apartment search, then Maine trip → "Are you moving or just vacationing?"
     - Conflicting information → Gently probe for accuracy
   - **Implementation:** Add validation logic to check for inconsistencies

---

## 📝 SESSION SUMMARY (43 Messages Tested)

**What Works Perfectly:**
- ✅ Unlimited conversation context
- ✅ Automatic memory storage (43 facts, 23 summaries)
- ✅ Perfect recall across 40+ messages
- ✅ Age correction (32→33) handled correctly
- ✅ Comprehensive summarization
- ✅ Emotional intelligence & empathy
- ✅ Natural topic switching
- ✅ Context integration (weaving multiple facts)
- ✅ Proactive behavior after shallow exchanges

**User Feedback:**
> "Overall, its really good (and really fun to see you both talk lol)"

**Status:** Core functionality EXCELLENT, ready for polish phase
