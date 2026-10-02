import json
import os
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
from google import genai

BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
BOT_USER_ID = os.environ.get("SLACK_BOT_USER_ID", "U0C48KSS0G3")
ADMIN_USER_ID = os.environ.get("SLACK_ADMIN_USER_ID", "U0BDPLQ226R") # Ali Aun
SOCIAL_CHANNEL_ID = os.environ.get("SLACK_SOCIAL_CHANNEL_ID", "C0B107Q0553")
DAILY_STATUS_CHANNEL_ID = os.environ.get("SLACK_DAILY_STATUS_CHANNEL_ID", "C0B9FAWPF0F")

ai_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

MODEL_LIST = ["gemini-2.5-flash-lite", "gemini-3.5-flash-lite", "gemini-flash-lite-latest"]

SYSTEM_PROMPT = """You are a highly capable AI assistant and Operations Coordinator for The Nevon & CrushSVG.

Key Guidelines:
1. Language Matching: If the user speaks in English, reply in professional English. If the user speaks in Roman Urdu, reply naturally in Roman Urdu.
2. NO Markdown Formatting: Do NOT use asterisks (** or *), hashtags (#), or underscores (_). Slack does not render them well. Output plain text only. Use numbers for lists and line breaks for spacing.
3. No Introductions: Do not introduce yourself. Never say "I am Ali Ai" or "Main The Nevon Agent hoon". Just directly answer the user's question or respond to their greeting. Act like a normal, helpful, and direct bot.
4. Provide accurate, clear, and direct answers. Keep the tone helpful, confident, and professional.

SPECIAL INSTRUCTION 1 - SOCIAL MEDIA POST FORMATTING:
When the user sends social media links or starts with 'post':
Analyze the raw links and output ONLY the formatted message blocks ready for Slack with NO extra conversational text.

Templates to follow strictly:

1. For Company Pages (The Nevon or CrushSVG):
Hey @channel ! must like the new post on [Company Name] [Platform] Page, and today we will be giving red tickets and penalty to anyone who have not been interacting with our recent post and they would have to work overtime.
[Link]
(Note: [Platform] must be Linkedin, Facebook, or Insta. [Company Name] is either 'The Nevon' or 'CrushSVG')

2. For Nadir Bhai's LinkedIn posts:
Hey @channel ! must like and comment on this the post on Nadir bhai Linkedin Account.
[Link]

3. For Ali Aun's LinkedIn posts / personal posts:
Hey @channel ! must like and comment on this post.
[Link]

Rules:
- Generate formatted blocks for ALL links in order, separated by a blank line.
- Do NOT use markdown links (no [text](url)), just output the raw clean URL directly on the line below the message.
- Output ONLY the formatted post blocks with NO intro and NO outro.

SPECIAL INSTRUCTION 2 - DAILY WORK REPORT FORMATTING:
When generating a daily work report for Ali Aun:
- Header:
Daily Work Report
Date: Month Day, Year

- STRICT PRIORITY ORDER (Substantial & high-value work FIRST, Social Media always LAST):
1. Email Template Development / Client Deliverables (e.g. Onboarding templates, revisions, pixel-perfect alignment)
2. AI & Automation (e.g. Agent training, Make.com automations, bot workflows)
3. QA Planning & Testing (e.g. QA testing plan for GTL x The Nevon partnership, bug tracking, audits)
4. Development & Fixes
5. Social Media (always at the very bottom, listing LinkedIn, Facebook, Instagram posts for Nadir Bhai, The Nevon, CrushSVG)

- Formatting Rules:
Use plain text categories with standard bullet points (-).
Write concise, professional, action-oriented bullet points (e.g., 'Reviewed client feedback...', 'Created and published...', 'Refined templates for pixel-perfect delivery...').
Output ONLY the formatted report with NO intro/outro so it is ready for Slack.
"""

PROCESSED_TS = set()

def clean_slack_text(raw_text):
    text = re.sub(r'<@[A-Z0-9]+>', '', raw_text).strip()
    text = re.sub(r'<((?:https?://)[^|>]+)(?:\|[^>]+)?>', r'\1', text)
    return text.strip()

def parse_time_to_epoch(text):
    pkt = timezone(timedelta(hours=5))
    now = datetime.now(pkt)
    
    m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text.lower())
    if not m:
        return None
    
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    ampm = m.group(3)
    
    if ampm == 'pm' and hour < 12:
        hour += 12
    elif ampm == 'am' and hour == 12:
        hour = 0
    elif not ampm and hour <= 7: # e.g. "6" or "7" assumed PM for evening shift
        hour += 12
        
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target.timestamp() <= (now.timestamp() + 30):
        target += timedelta(days=1)
        
    return int(target.timestamp()), target.strftime("%I:%M %p")

def get_slack_history(channel_id, thread_ts=None):
    try:
        if thread_ts:
            url = f"https://slack.com/api/conversations.replies?channel={channel_id}&ts={thread_ts}&limit=6"
        else:
            url = f"https://slack.com/api/conversations.history?channel={channel_id}&limit=6"
        
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {BOT_TOKEN}"})
        with urllib.request.urlopen(req, timeout=2) as res:
            data = json.loads(res.read().decode("utf-8"))
            if data.get("ok"):
                messages = data.get("messages", [])
                if not thread_ts:
                    messages.reverse()
                
                transcript = []
                for m in messages[-6:]:
                    speaker = "Agent" if m.get("bot_id") else "User"
                    m_text = clean_slack_text(m.get("text", ""))
                    if m_text:
                        transcript.append(f"{speaker}: {m_text}")
                return "\n".join(transcript)
    except Exception as e:
        print("History error:", e)
    return ""

def extract_last_report_from_history(history_text):
    if not history_text:
        return ""
    # Find block starting with Daily Work Report
    if "Daily Work Report" in history_text:
        parts = history_text.split("Daily Work Report")
        last_part = parts[-1]
        # remove review footer if present
        cleaned = "Daily Work Report" + last_part.split("---------------------------------")[0].split("Aapka Daily Work Report")[0].strip()
        return cleaned
    return ""

def generate_ai_reply(user_text, history_context=""):
    clean_text = clean_slack_text(user_text)
    if not clean_text:
        clean_text = "hello"
    
    if not ai_client:
        return "The Nevon Agent: (GEMINI_API_KEY not configured)."

    today_str = datetime.now().strftime("%B %d, %Y")
    prompt_parts = [SYSTEM_PROMPT, f"Today's Date: {today_str}"]
    if history_context:
        prompt_parts.append(f"--- Recent Conversation Context ---\n{history_context}\n-----------------------------------")
    
    prompt_parts.append(f"Current User Message: {clean_text}")
    full_prompt = "\n\n".join(prompt_parts)

    errors = []
    
    for model_name in MODEL_LIST:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=full_prompt
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            errors.append(f"{model_name}: {str(e)}")
            continue

    return f"The Nevon Agent: System is currently overloaded. Please try again in a few seconds! (Errors: {errors})"

def post_slack_message(channel, text, thread_ts=None):
    if not BOT_TOKEN:
        return False
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req) as res:
            res_data = json.loads(res.read().decode("utf-8"))
            return res_data.get("ok", False)
    except Exception as e:
        print(f"Error posting to Slack: {e}", flush=True)
        return False

def schedule_slack_message(channel, text, post_at_epoch):
    if not BOT_TOKEN:
        return False
    url = "https://slack.com/api/chat.scheduleMessage"
    headers = {
        "Authorization": f"Bearer {BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "channel": channel,
        "text": text,
        "post_at": post_at_epoch
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req) as res:
            res_data = json.loads(res.read().decode("utf-8"))
            return res_data.get("ok", False)
    except Exception as e:
        print(f"Error scheduling in Slack: {e}", flush=True)
        return False

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        try:
            with open('/tmp/logs.txt', 'r') as f:
                logs = f.read()
        except Exception:
            logs = "No logs yet."
        
        self.wfile.write(f'The Nevon Agent is live 24/7 on Vercel!\n\nLogs:\n{logs}'.encode())

    def log_request(self, msg):
        try:
            with open('/tmp/logs.txt', 'a') as f:
                f.write(msg + "\n")
        except Exception:
            pass

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        
        self.log_request(f"POST received: {body[:200]}...")
        
        try:
            data = json.loads(body)
        except Exception as e:
            print("JSON parse error:", e, flush=True)
            self.send_response(400)
            self.end_headers()
            return

        # 1. Slack URL Verification Challenge
        if data.get("type") == "url_verification":
            challenge = data.get("challenge")
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"challenge": challenge}).encode())
            return

        # 2. Extract Event Data
        event = data.get("event", {})
        event_type = event.get("type")
        user = str(event.get("user", ""))
        channel = str(event.get("channel", ""))
        text = event.get("text", "")
        ts = event.get("ts")
        thread_ts = event.get("thread_ts")
        subtype = event.get("subtype")
        
        if not event or user == BOT_USER_ID or event.get("bot_id") or subtype == "bot_message":
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ignored"}).encode())
            return
            
        if ts and ts in PROCESSED_TS:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "duplicate"}).encode())
            return
        if ts:
            PROCESSED_TS.add(ts)

        is_dm = channel.startswith("D") or event.get("channel_type") == "im"
        is_mention = event_type == "app_mention" or f"<@{BOT_USER_ID}>" in text

        debug_info = {}
        if is_dm or is_mention:
            try:
                history = get_slack_history(channel, thread_ts)
                cleaned_user_text = clean_slack_text(text).lower()
                is_admin = (user == ADMIN_USER_ID)
                
                # Check for explicit schedule request on previous report
                # e.g. "schedule for 6pm", "schedule 6pm", "schedule 6:30 pm"
                if is_dm and is_admin and cleaned_user_text.startswith("schedule"):
                    parsed_time = parse_time_to_epoch(cleaned_user_text)
                    last_report = extract_last_report_from_history(history)
                    
                    if parsed_time and last_report:
                        epoch, formatted_time = parsed_time
                        ok = schedule_slack_message(DAILY_STATUS_CHANNEL_ID, last_report, epoch)
                        if ok:
                            dm_reply = f"Aapka Daily Work Report aaj {formatted_time} baje ke liye schedule ho gaya hai! ?\nSlack theek us waqt #daily-status channel mein bhej dega."
                        else:
                            dm_reply = "Scheduling mein thora masla aya, please dobara time specify karein."
                    elif not last_report:
                        dm_reply = "Pehle mujhe eport: likh kar aaj ke points dein taake main draft bana saku, phir schedule karein!"
                    else:
                        dm_reply = "Time samajh nahi aya. Please aese likhein: schedule for 6pm ya schedule 6:30pm"
                    
                    post_slack_message(channel, dm_reply)

                # Check for "post now" on previous report
                elif is_dm and is_admin and cleaned_user_text in ["post now", "post report", "approve", "bhej do", "send now"]:
                    last_report = extract_last_report_from_history(history)
                    if last_report:
                        posted_ok = post_slack_message(DAILY_STATUS_CHANNEL_ID, last_report)
                        dm_reply = "Maine aapka Daily Work Report #daily-status channel mein post kar diya hai! ??" if posted_ok else "Post karne mein error aya."
                    else:
                        dm_reply = "Pehle eport: likh kar apne points bhein!"
                    post_slack_message(channel, dm_reply)

                # Social Post Command
                elif "http" in text and (cleaned_user_text.startswith("post") or any(w in cleaned_user_text for w in ["social", "bhej", "send", "share"])):
                    reply = generate_ai_reply(text, history)
                    if is_admin:
                        # Check if a schedule time was specified e.g. "post at 3pm https://..."
                        if " at " in cleaned_user_text or " for " in cleaned_user_text or "schedule" in cleaned_user_text:
                            parsed_time = parse_time_to_epoch(cleaned_user_text)
                            if parsed_time:
                                epoch, formatted_time = parsed_time
                                ok = schedule_slack_message(SOCIAL_CHANNEL_ID, reply, epoch)
                                dm_reply = f"Social post aaj {formatted_time} baje ke liye schedule ho gayi hai! ?\n\nPreview:\n{reply}" if ok else f"Formatted text:\n\n{reply}"
                            else:
                                posted_ok = post_slack_message(SOCIAL_CHANNEL_ID, reply)
                                dm_reply = f"Maine ye post #social channel mein bhej di hai! ?\n\nPreview:\n{reply}" if posted_ok else f"Formatted text:\n\n{reply}"
                        else:
                            posted_ok = post_slack_message(SOCIAL_CHANNEL_ID, reply)
                            dm_reply = f"Maine ye post #social channel mein bhej di hai! ?\n\nPreview:\n{reply}" if posted_ok else f"Formatted text:\n\n{reply}"
                    else:
                        dm_reply = f"Aap ke paas #social channel mein broadcast karne ki permission nahi hai. Sirf Ali Aun ye kar sakte hain.\n\nPreview:\n{reply}"
                    
                    post_slack_message(channel, dm_reply, thread_ts=thread_ts if not is_dm else None)

                # Daily Status Generation & Review Request
                elif cleaned_user_text.startswith("report") or cleaned_user_text.startswith("status") or "daily report" in cleaned_user_text:
                    reply = generate_ai_reply(text, history)
                    if is_admin:
                        review_prompt = f"Aapka Daily Work Report tayyar hai! ?? Review kar lein:\n\n{reply}\n\n---------------------------------\nAgar theek hai to reply karein:\n• post now (ab post karne ke liye)\n• schedule for 6pm (ya koi bhi time jaise schedule 6:30pm)"
                        post_slack_message(channel, review_prompt, thread_ts=thread_ts if not is_dm else None)
                    else:
                        post_slack_message(channel, reply, thread_ts=thread_ts if not is_dm else None)

                else:
                    # General Conversational Chat
                    reply = generate_ai_reply(text, history)
                    reply_thread = thread_ts if not is_dm else None
                    post_slack_message(channel, reply, thread_ts=reply_thread)
                    
            except Exception as e:
                debug_info["error"] = str(e)
                print("Handler error:", e, flush=True)

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "debug": debug_info}).encode())
