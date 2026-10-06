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
5. NEVER claim you sent, posted, scheduled, deleted, or followed up on anything. In this conversation you can only reply with text. If the user asks you to message someone or a channel and you are reading this, it means the request was not understood as a command. Reply briefly that you could not identify the channel, and ask them to write it like: crushsvg channel me ahtisham aur irtaza ko msg bhej ke tickets ka status kya hai.
6. CONTEXTUAL REPLIES & IGNORING: If users are talking to each other AND it has nothing to do with your last message, reply with EXACTLY the word: IGNORE_MESSAGE. BUT if a user is providing a status update, answering your question, or making a comment after you spoke, YOU MUST REPLY. DO NOT IGNORE IT. Act as the coordinator and acknowledge their update.

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
(Note: Any post mentioned as Nadir Bhai, or shortlinks like lnkd.in posted in morning/evening, must strictly use Nadir Bhai's template)

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

SPECIAL INSTRUCTION 3 - HANDLING REPLIES IN TEAM CHANNELS:
When you see your own previous message ("Agent: ...") asking for an update, and the user's new message is answering it:
- Acknowledge their reply briefly (1 sentence) as a helpful team coordinator.
- If they need time: "Noted, take your time but please keep us updated."
- If they report an issue/blocker: "Got it. I will notify Ali to look into this."
- If they say it's done: "Great work! I'll inform the team."
- Adopt the typical communication style of The Nevon workspace: concise, direct, and slightly informal but professional (e.g. 'Great, let us know when it is done', 'Okay, we will skip this for now'). Avoid robotic corporate language.

SPECIAL INSTRUCTION 4 - THE NEVON COMPANY CONTEXT:
You have deep knowledge about the company "The Nevon". Use this context if someone asks about the company, its pages, links, or procedures:
- Company Name: THE NEVON (The New Vision)
- Founder: Sardar Muhammad Nadir
- Mission: Transform youth potential into productive leadership.
- Vision: Create a generation that earns through skill, integrity, and innovation rather than shortcuts and scams.
- Website: thenevon.com
- Contact: nadirali0172@gmail.com, LinkedIn: linkedin.com/in/nadir1214
- Target Audience: Teenagers (15-18), University Students, Fresh Graduates, Underserved Youth.
- Operations: We handle Career Discovery, Leadership Development, Practical Skill Training, Mentorship.
- Tools: We use Figma for designs, Vercel for deployments, OpenPhone for virtual numbers, TikTok Business Center for TikTok, and YouTube Studio (Brand Accounts) for YouTube.
- Tone for Morning Greetings: If a team member says "Good morning" or similar early in the day, reply with a very warm, sweet, and motivating good morning message (e.g., "Good morning! Hope you have a productive and great day ahead!").
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
    elif not ampm and hour <= 7:
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

def extract_last_social_post(history_text):
    if not history_text:
        return ""
    matches = re.findall(r'(Hey (?:@channel|<!channel>)[^\n]*\n[^\n]+)', history_text)
    if matches:
        return matches[-1].strip()
    return ""

def extract_last_report_from_history(history_text):
    if not history_text:
        return ""
    if "Daily Work Report" in history_text:
        parts = history_text.split("Daily Work Report")
        last_part = parts[-1]
        cleaned = "Daily Work Report" + last_part.split("---------------------------------")[0].split("Aapka Daily Work Report")[0].strip()
        return cleaned
    return ""

def get_last_bot_message_in_channel(channel_id):
    url = f"https://slack.com/api/conversations.history?channel={channel_id}&limit=15"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {BOT_TOKEN}"})
    try:
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode("utf-8"))
            if data.get("ok"):
                for m in data.get("messages", []):
                    if m.get("bot_id") or m.get("user") == BOT_USER_ID:
                        return m.get("ts"), m.get("text", "")[:60]
    except Exception as e:
        print("get_last_bot_message error:", e)
    return None, None

def delete_slack_message(channel, ts):
    if not BOT_TOKEN or not ts:
        return False
    url = "https://slack.com/api/chat.delete"
    headers = {
        "Authorization": f"Bearer {BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {"channel": channel, "ts": ts}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req) as res:
            res_data = json.loads(res.read().decode("utf-8"))
            return res_data.get("ok", False)
    except Exception as e:
        print(f"Error deleting message: {e}", flush=True)
        return False

def cancel_scheduled_messages(channel_id):
    url = f"https://slack.com/api/chat.scheduledMessages.list?channel={channel_id}"
    headers = {"Authorization": f"Bearer {BOT_TOKEN}"}
    req = urllib.request.Request(url, headers=headers)
    count = 0
    try:
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode("utf-8"))
            for sm in data.get("scheduled_messages", []):
                del_url = "https://slack.com/api/chat.deleteScheduledMessage"
                del_payload = json.dumps({"channel": channel_id, "scheduled_message_id": sm["id"]}).encode("utf-8")
                del_req = urllib.request.Request(del_url, data=del_payload, headers={**headers, "Content-Type": "application/json"})
                with urllib.request.urlopen(del_req) as del_res:
                    res_data = json.loads(del_res.read().decode("utf-8"))
                    if res_data.get("ok"):
                        count += 1
    except Exception as e:
        print("Cancel scheduled error:", e)
    return count

# ==========================================
# RELAY HELPERS (post a message into any channel on Ali's instruction)
# ==========================================
# Static directory (bot token lacks users:read scope). Keys are lowercase name fragments.
TEAM_DIRECTORY = {
    "U0B11HVF5AA": ["sardar muhammad nadir", "nadir"],
    "U0B1GJBD9NV": ["fatima irfan", "fatima"],
    "U0B89NBCVQA": ["azan mehdi", "azan"],
    "U0B967U99DW": ["muhammad umar", "umar", "umer"],
    "U0B9E85N0UV": ["mishal"],
    "U0BDBJLULET": ["sultan ali", "sultan"],
    "U0BG93NG2UU": ["muhammad aswad khan", "aswad"],
    "U0C1FQCECLV": ["joun ahmed", "joun"],
    "U0C205GFWQZ": ["muhammad arham athar", "arham athar", "arham"],
    "U0C2W4D21PH": ["muhammad irtaza", "irtaza"],
    "U0C43V57UDN": ["hafiz arslan", "arslan"],
    "U0C4J8PEY1M": ["abdul moiz shahzad", "moiz shahzad"],
    "U0C4JA7HPPW": ["abdul moiz", "moiz"],
    "U0C5LQ5331U": ["khalid niaz", "khalid"],
    "U0C5QKUBLU8": ["ahtisham ul haq", "ahtisham", "ehtisham"],
}

RELAY_VERBS = ["msg", "message", "bhej", "phenk", "phek", "follow up", "followup", "follow-up",
               "pooch", "puch", "pucho", "poocho", "bol", "keh", "kah", "tell", "ask", "remind",
               "yaad", "status le", "update le", "inform", "bata", "likh"]

def get_bot_channels():
    try:
        url = "https://slack.com/api/conversations.list?types=public_channel,private_channel&limit=200&exclude_archived=true"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {BOT_TOKEN}"})
        with urllib.request.urlopen(req, timeout=3) as res:
            data = json.loads(res.read().decode("utf-8"))
            if data.get("ok"):
                return [(c["id"], c["name"]) for c in data.get("channels", []) if c.get("is_member")]
    except Exception as e:
        print("Channel list error:", e)
    return []

def find_channel_in_text(text, channels):
    # Explicit Slack channel link: <#C123|name> or <#C123>
    m = re.search(r'<#(C[A-Z0-9]+)(?:\|([^>]*))?>', text)
    if m:
        cid = m.group(1)
        for c_id, c_name in channels:
            if c_id == cid:
                return c_id, c_name
        return cid, m.group(2) or cid
    lower = text.lower()
    # Longest names first so 'thenevon-website' wins over 'thenevon'
    for c_id, c_name in sorted(channels, key=lambda c: -len(c[1])):
        variants = {c_name, c_name.replace("-", " "), c_name.replace("-", "")}
        for v in variants:
            if re.search(r'(?<![a-z0-9])#?' + re.escape(v) + r'(?![a-z0-9])', lower):
                return c_id, c_name
    return None, None

def has_relay_intent(text_lower):
    return any(re.search(r'(?<![a-z])' + re.escape(v), text_lower) for v in RELAY_VERBS)

def find_mentioned_users(text_lower):
    found = []
    for uid, names in TEAM_DIRECTORY.items():
        if any(re.search(r'(?<![a-z])' + re.escape(n) + r'(?![a-z])', text_lower) for n in names):
            found.append(uid)
    # 'abdul moiz' also matches 'abdul moiz shahzad' - drop the shorter one if longer matched
    if "U0C4J8PEY1M" in found and "U0C4JA7HPPW" in found and "shahzad" in text_lower:
        found.remove("U0C4JA7HPPW")
    return found

def compose_relay_message(instruction, mention_ids, channel_name, history_context=""):
    mentions = " ".join(f"<@{u}>" for u in mention_ids)
    prompt = f"""You write Slack messages on behalf of Ali Aun (Operations / QA lead at The Nevon & CrushSVG).
Ali gave you an instruction (often in Roman Urdu) describing a message to post in the #{channel_name} channel.
Write the ACTUAL message Ali wants posted, addressed directly to the people, in clear, polite, professional English.

Rules:
- Output ONLY the message text. No preface, no quotes, no explanation.
- No markdown (no asterisks, underscores, hashtags). Plain text only.
- Keep it short and direct (1 to 3 sentences). Do not invent deadlines or facts not in the instruction.
- The following Slack user IDs were extracted from Ali's message: {mentions}. Use these exact IDs to tag people (e.g. "Hey <@U123>"). Do NOT repeat their names at the end of the sentence.

Recent DM context (use it to understand follow-ups like 'send it there'):
{history_context}

Ali's instruction: {instruction}"""
    if not ai_client:
        return None
    for model_name in MODEL_LIST:
        try:
            response = ai_client.models.generate_content(model=model_name, contents=prompt)
            if response and response.text:
                msg = response.text.strip().strip('"').replace("**", "")
                if mentions and not all(f"<@{u}>" in msg for u in mention_ids):
                    msg = mentions + " " + msg
                return msg
        except Exception as e:
            print(f"Relay compose error {model_name}:", e)
            continue
    return None

def compose_dm_message(instruction, history_context=""):
    prompt = f"""You are helping Ali extract the exact direct message he wants to send to someone.
Ali gave you an instruction in Roman Urdu/English (e.g., 'umer ko likh hi lol' or 'umer ko msg karo hi lol').
Extract ONLY the actual message meant for the person. Do NOT include the command part like 'umer ko likh' or 'isay keh'.
Do NOT add any quotes or extra words. It should be exactly what Ali wants to tell them.

Recent DM context:
{history_context}

Ali's instruction: {instruction}"""
    if not ai_client:
        return None
    for model_name in MODEL_LIST:
        try:
            response = ai_client.models.generate_content(model=model_name, contents=prompt)
            if response and response.text:
                msg = response.text.strip().strip('"').replace("**", "")
                return msg
        except Exception as e:
            print(f"DM compose error {model_name}:", e)
            continue
    return None

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

        if data.get("type") == "url_verification":
            challenge = data.get("challenge")
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"challenge": challenge}).encode())
            return

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

        is_potential_reply = False
        if not is_dm and not is_mention and event_type == "message" and not event.get("bot_id") and subtype != "bot_message":
            if channel not in (SOCIAL_CHANNEL_ID, DAILY_STATUS_CHANNEL_ID):
                is_potential_reply = True

        debug_info = {}
        if is_dm or is_mention or is_potential_reply:
            try:
                history = get_slack_history(channel, thread_ts)
                
                if is_potential_reply:
                    lines = [l for l in history.split('\n') if l.strip()]
                    if any(l.startswith("Agent:") for l in lines):
                        is_mention = True
                    elif thread_ts and lines and lines[0].startswith("Agent:"):
                        is_mention = True
                        
                    if not is_mention:
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "ignored"}).encode())
                        return
                cleaned_user_text = clean_slack_text(text).lower()
                is_admin = (user == ADMIN_USER_ID)

                # ---- Pre-compute routing inputs ----
                has_curr_links = bool(re.search(r'(?:https?://|lnkd\.in/|facebook\.com/|instagram\.com/)[^\s]+', clean_slack_text(text)))
                has_hist_links = bool(re.search(r'(?:https?://|lnkd\.in/|facebook\.com/|instagram\.com/)[^\s]+', history))
                has_social_intent = (
                    cleaned_user_text.startswith("post") or
                    any(w in cleaned_user_text for w in ["social", "bhej", "send", "share", "channel"])
                )

                relay_channel_id, relay_channel_name, relay_mentions, relay_instruction = None, None, [], ""
                relay_dm_user_ids = []
                bot_channels = []
                is_command_word = cleaned_user_text.startswith(("delete", "undo", "remove", "schedule", "report", "status", "post"))
                if is_admin and is_dm and not has_curr_links and not is_command_word and has_relay_intent(cleaned_user_text):
                    bot_channels = [c for c in get_bot_channels() if c[0] not in (SOCIAL_CHANNEL_ID, DAILY_STATUS_CHANNEL_ID)]
                    relay_channel_id, relay_channel_name = find_channel_in_text(text, bot_channels)
                    source_text = cleaned_user_text
                    relay_instruction = clean_slack_text(text)
                    if not relay_channel_id:
                        relay_dm_user_ids = find_mentioned_users(source_text)
                        if not relay_dm_user_ids:
                            # Follow-up like "msg phenk na wahan pr": look back at Ali's recent messages
                            user_lines = [l[len("User: "):] for l in history.split("\n") if l.startswith("User: ")]
                            for prev in reversed(user_lines[:-1] if user_lines and user_lines[-1].lower() == cleaned_user_text else user_lines):
                                cid, cname = find_channel_in_text(prev, bot_channels)
                                if cid:
                                    relay_channel_id, relay_channel_name = cid, cname
                                    source_text = prev.lower() + " " + cleaned_user_text
                                    relay_instruction = prev + "\n(Follow-up: " + clean_slack_text(text) + ")"
                                    break
                                uids = find_mentioned_users(prev.lower())
                                if uids:
                                    relay_dm_user_ids = uids
                                    source_text = prev.lower() + " " + cleaned_user_text
                                    relay_instruction = prev + "\n(Follow-up: " + clean_slack_text(text) + ")"
                                    break
                    if relay_channel_id:
                        tagged = [u for u in re.findall(r'<@([A-Z0-9]+)>', text) if u != BOT_USER_ID]
                        relay_mentions = list(dict.fromkeys(tagged + find_mentioned_users(source_text)))
                
                # ==========================================
                # 1. DELETE / UNDO COMMANDS (Admin Only)
                # ==========================================
                if is_admin and (cleaned_user_text.startswith("delete") or cleaned_user_text.startswith("undo") or cleaned_user_text.startswith("remove")):
                    named_cid, named_cname = find_channel_in_text(text, [c for c in get_bot_channels() if c[0] not in (SOCIAL_CHANNEL_ID, DAILY_STATUS_CHANNEL_ID)])
                    # Delete last bot message in a specifically named channel (e.g. "delete crushsvg")
                    if named_cid and "post" not in cleaned_user_text:
                        msg_ts, msg_preview = get_last_bot_message_in_channel(named_cid)
                        if msg_ts and delete_slack_message(named_cid, msg_ts):
                            dm_reply = f"#{named_cname} se bot ka aakhri message delete kar diya.\n(Text: {msg_preview})"
                        else:
                            dm_reply = f"#{named_cname} mein bot ka koi haal hi ka message nahi mila."
                    # Delete Status / Report
                    elif any(w in cleaned_user_text for w in ["status", "report", "daily"]):
                        msg_ts, msg_preview = get_last_bot_message_in_channel(DAILY_STATUS_CHANNEL_ID)
                        if msg_ts:
                            deleted = delete_slack_message(DAILY_STATUS_CHANNEL_ID, msg_ts)
                            dm_reply = f"Maine #daily-status channel se aapki aakhri report delete kar di hai! ???\n(Text: {msg_preview})" if deleted else "Report delete karne mein masla aya."
                        else:
                            dm_reply = "Channel #daily-status mein bot ka koi haal hi mein bheja hua message nahi mila."
                    
                    # Cancel Scheduled Posts
                    elif "schedule" in cleaned_user_text:
                        cancelled_status = cancel_scheduled_messages(DAILY_STATUS_CHANNEL_ID)
                        cancelled_social = cancel_scheduled_messages(SOCIAL_CHANNEL_ID)
                        total = cancelled_status + cancelled_social
                        dm_reply = f"Aapke {total} scheduled message(s) cancel kar diye gaye hain! ??" if total > 0 else "Koi pending scheduled message nahi mila."
                    
                    # Delete Social Post or Last Post (Default)
                    else:
                        msg_ts, msg_preview = get_last_bot_message_in_channel(SOCIAL_CHANNEL_ID)
                        if msg_ts:
                            deleted = delete_slack_message(SOCIAL_CHANNEL_ID, msg_ts)
                            dm_reply = f"Maine #social channel se aakhri post delete kar di hai! ???\n(Text: {msg_preview})" if deleted else "Message delete karne mein masla aya."
                        else:
                            # fallback: check current channel
                            cur_ts, cur_preview = get_last_bot_message_in_channel(channel)
                            if cur_ts:
                                deleted = delete_slack_message(channel, cur_ts)
                                dm_reply = "Maine is chat se aakhri message delete kar diya hai! ???" if deleted else "Delete nahi ho saka."
                            else:
                                dm_reply = "Koi haal hi ka bot message nahi mila jisko delete kiya ja sake."
                    
                    post_slack_message(channel, dm_reply, thread_ts=thread_ts if not is_dm else None)

                # ==========================================
                # 2. SCHEDULE COMMAND (On Reviewed Report)
                # ==========================================
                elif is_dm and is_admin and cleaned_user_text.startswith("schedule"):
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
                        dm_reply = "Pehle mujhe 'report:' likh kar points dein taake main draft bana saku, phir schedule karein!"
                    else:
                        dm_reply = "Time samajh nahi aya. Please aese likhein: schedule for 6pm ya schedule 6:30pm"
                    
                    post_slack_message(channel, dm_reply)

                # ==========================================
                # 3. POST NOW COMMAND (On Reviewed Report)
                # ==========================================
                elif is_dm and is_admin and cleaned_user_text in ["post now", "post report", "approve", "bhej do", "send now"]:
                    last_report = extract_last_report_from_history(history)
                    if last_report:
                        posted_ok = post_slack_message(DAILY_STATUS_CHANNEL_ID, last_report)
                        dm_reply = "Maine aapka Daily Work Report #daily-status channel mein post kar diya hai! ??" if posted_ok else "Post karne mein error aya."
                    else:
                        dm_reply = "Pehle 'report:' likh kar apne points bhejein!"
                    post_slack_message(channel, dm_reply)

                # ==========================================
                # 4. CHANNEL RELAY (Admin asks bot to message people in a channel)
                # ==========================================
                elif is_admin and relay_channel_id:
                    composed = compose_relay_message(relay_instruction, relay_mentions, relay_channel_name, history)
                    if composed:
                        posted_ok = post_slack_message(relay_channel_id, composed)
                        if posted_ok:
                            dm_reply = f"Bhej diya <#{relay_channel_id}> mein:\n\n{composed}\n\n(Wapas lena ho to likhein: delete {relay_channel_name})"
                        else:
                            dm_reply = f"#{relay_channel_name} mein post nahi ho saka. Check karein ke bot us channel mein added hai."
                    else:
                        dm_reply = "Message compose nahi ho saka (AI busy hai). Thori der baad dobara try karein."
                    post_slack_message(channel, dm_reply, thread_ts=thread_ts if not is_dm else None)

                # ==========================================
                # 4b. USER DM RELAY (Admin asks bot to DM a user directly)
                # ==========================================
                elif is_admin and relay_dm_user_ids:
                    composed = compose_dm_message(relay_instruction, history)
                    if composed:
                        success_users = []
                        fail_users = []
                        for uid in relay_dm_user_ids:
                            if post_slack_message(uid, composed):
                                success_users.append(uid)
                            else:
                                fail_users.append(uid)
                        
                        dm_reply = ""
                        if success_users:
                            mentions = " ".join(f"<@{u}>" for u in success_users)
                            dm_reply += f"DM bhej diya inko: {mentions}\n\nMessage:\n{composed}"
                        if fail_users:
                            mentions = " ".join(f"<@{u}>" for u in fail_users)
                            dm_reply += f"\n\nInko DM nahi ja saka: {mentions}"
                    else:
                        dm_reply = "Message extract nahi ho saka (AI busy hai). Thori der baad dobara try karein."
                    
                    post_slack_message(channel, dm_reply, thread_ts=thread_ts if not is_dm else None)

                # ==========================================
                # 5. SOCIAL BROADCASTING COMMAND
                # ==========================================
                elif is_admin and (has_curr_links or has_hist_links) and has_social_intent:
                    # If current text doesn't contain the link, combine with history for AI
                    ai_input = text
                    if not has_curr_links and has_hist_links:
                        ai_input = f"Format and post this to social based on recent context: {text}"
                    
                    reply = generate_ai_reply(ai_input, history)
                    
                    # Ensure reply contains formatted post
                    if "Hey @channel" not in reply and "Hey <!channel>" not in reply:
                        # Extract previous post from history if available
                        prev_post = extract_last_social_post(history) if "extract_last_social_post" in globals() else None
                        if prev_post:
                            reply = prev_post
                    
                    if is_admin:
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

                # ==========================================
                # 5. DAILY STATUS GENERATION (REVIEW REQUEST)
                # ==========================================
                elif cleaned_user_text.startswith("report") or cleaned_user_text.startswith("status") or "daily report" in cleaned_user_text:
                    reply = generate_ai_reply(text, history)
                    if is_admin:
                        review_prompt = f"Aapka Daily Work Report tayyar hai! ?? Review kar lein:\n\n{reply}\n\n---------------------------------\nAgar theek hai to reply karein:\n- post now (ab post karne ke liye)\n- schedule for 6pm (ya koi bhi time jaise schedule 6:30pm)\n- delete report (agar delete karna ho)"
                        post_slack_message(channel, review_prompt, thread_ts=thread_ts if not is_dm else None)
                    else:
                        post_slack_message(channel, reply, thread_ts=thread_ts if not is_dm else None)

                # ==========================================
                # 6. GENERAL CONVERSATION
                # ==========================================
                else:
                    ai_input = text
                    if is_potential_reply:
                        ai_input = f"[SYSTEM NOTE: You recently spoke in this channel. Review the history. If the user's message is answering you, providing a status update, or directed at you, YOU MUST REPLY (do not output IGNORE_MESSAGE). If they are talking to someone else entirely, output IGNORE_MESSAGE.]\n\n{text}"
                    reply = generate_ai_reply(ai_input, history)
                    if reply.strip() != "IGNORE_MESSAGE":
                        reply_thread = thread_ts if not is_dm else None
                        post_slack_message(channel, reply, thread_ts=reply_thread)
                    
            except Exception as e:
                debug_info["error"] = str(e)
                print("Handler error:", e, flush=True)

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "debug": debug_info}).encode())
