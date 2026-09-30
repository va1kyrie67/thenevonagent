import json
import os
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler
from google import genai

BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
BOT_USER_ID = os.environ.get("SLACK_BOT_USER_ID", "U0C48KSS0G3")

ai_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None
MODEL_LIST = ["gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash"]

SYSTEM_PROMPT = """You are The Nevon Agent (Ali Ai), a senior AI Software Architect, Senior Product Designer, and Business Strategist.
You specialize in clean code, robust system design, UI/UX systems, business workflows, and technical problem solving.

Key Guidelines:
1. Provide comprehensive, accurate, structured, and highly intelligent answers. Use bold headers, bullet points, and code blocks where applicable.
2. If the user asks in Roman Urdu (e.g. "kya haal hai", "kaise ho", "help kar de"), respond warmly and professionally in Roman Urdu.
3. If the user provides a prompt or technical question (e.g. coding, design systems, workflows, automation), break it down step-by-step with actionable insights.
4. Keep the tone helpful, confident, clear, and professional.
"""

# Track processed timestamps in warm serverless instance
PROCESSED_TS = set()

def generate_ai_reply(user_text):
    clean_text = user_text.replace(f"<@{BOT_USER_ID}>", "").strip()
    if not clean_text:
        clean_text = "hello"
    
    if not ai_client:
        return f"🤖 *The Nevon Agent:* Received: *'{clean_text}'*. (GEMINI_API_KEY is not configured)."

    full_prompt = f"{SYSTEM_PROMPT}\n\nUser Question:\n{clean_text}"

    for model_name in MODEL_LIST:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=full_prompt
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            print(f"Model {model_name} error: {e}", flush=True)
            continue

    return f"🤖 *The Nevon Agent:* Received your request: '{clean_text}'. How can I assist you further?"

def post_slack_message(channel, text, thread_ts=None):
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN is missing", flush=True)
        return
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "channel": channel,
        "text": text
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req) as res:
            res_data = json.loads(res.read().decode("utf-8"))
            print("Slack postMessage response:", res_data, flush=True)
    except Exception as e:
        print(f"Error posting to Slack: {e}", flush=True)

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write('The Nevon Agent is live 24/7 on Vercel Serverless!'.encode())

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        
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

        # 2. IMMEDIATE ACK-FIRST PATTERN:
        # Acknowledge Slack immediately within 30ms to prevent the 3-second HTTP timeout!
        ack_payload = json.dumps({"status": "ok"}).encode()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Content-Length', str(len(ack_payload)))
        self.end_headers()
        self.wfile.write(ack_payload)
        self.wfile.flush()

        # 3. Extract and Process Event Asynchronously
        event = data.get("event", {})
        event_type = event.get("type")
        user = event.get("user")
        channel = str(event.get("channel", ""))
        text = event.get("text", "")
        ts = event.get("ts")
        thread_ts = event.get("thread_ts")
        subtype = event.get("subtype")

        # Ignore bot's own messages or sub-events
        if not event or user == BOT_USER_ID or event.get("bot_id") or subtype == "bot_message":
            return

        # Deduplicate
        if ts and ts in PROCESSED_TS:
            return
        if ts:
            PROCESSED_TS.add(ts)

        # Check if direct message (D...) or mention
        is_dm = channel.startswith("D") or event.get("channel_type") == "im"
        is_mention = event_type == "app_mention" or f"<@{BOT_USER_ID}>" in text

        if is_dm or is_mention:
            print(f"[PROCESSING EVENT] Channel: {channel} | User: {user} | Text: {text}", flush=True)
            reply = generate_ai_reply(text)
            reply_thread = thread_ts if not is_dm else None
            post_slack_message(channel, reply, thread_ts=reply_thread)
