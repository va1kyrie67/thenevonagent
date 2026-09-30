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

# Ultra-fast models available in 2026
MODEL_LIST = ["gemini-2.5-flash-lite", "gemini-3.5-flash-lite", "gemini-flash-lite-latest"]

SYSTEM_PROMPT = """You are a highly capable AI assistant.

Key Guidelines:
1. Language Matching: If the user speaks in English, reply in professional English. If the user speaks in Roman Urdu, reply naturally in Roman Urdu.
2. NO Markdown Formatting: Do NOT use asterisks (** or *), hashtags (#), or underscores (_). Slack does not render them well. Output plain text only. Use numbers for lists and line breaks for spacing.
3. No Introductions: Do not introduce yourself. Never say "I am Ali Ai" or "Main The Nevon Agent hoon". Just directly answer the user's question or respond to their greeting. Act like a normal, helpful, and direct bot.
4. Provide accurate, clear, and direct answers. Keep the tone helpful, confident, and professional.
"""

PROCESSED_TS = set()

def generate_ai_reply(user_text):
    clean_text = user_text.replace(f"<@{BOT_USER_ID}>", "").strip()
    if not clean_text:
        clean_text = "hello"
    
    if not ai_client:
        return f"🤖 *The Nevon Agent:* (GEMINI_API_KEY not configured)."

    full_prompt = f"{SYSTEM_PROMPT}\n\nUser Question:\n{clean_text}"

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

    return f"🤖 *The Nevon Agent:* System is currently overloaded. Please try again in a few seconds! (Errors: {errors})"

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
            print("Slack postMessage success:", res_data.get("ok"), flush=True)
    except Exception as e:
        print(f"Error posting to Slack: {e}", flush=True)

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
        user = event.get("user")
        channel = str(event.get("channel", ""))
        text = event.get("text", "")
        ts = event.get("ts")
        thread_ts = event.get("thread_ts")
        subtype = event.get("subtype")
        
        # Ignore bot's own messages or sub-events
        if not event or user == BOT_USER_ID or event.get("bot_id") or subtype == "bot_message":
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ignored"}).encode())
            return
            
        # Deduplicate to prevent double-posting
        if ts and ts in PROCESSED_TS:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "duplicate"}).encode())
            return
        if ts:
            PROCESSED_TS.add(ts)

        # Check if direct message (D...) or mention
        is_dm = channel.startswith("D") or event.get("channel_type") == "im"
        is_mention = event_type == "app_mention" or f"<@{BOT_USER_ID}>" in text

        debug_info = {}
        if is_dm or is_mention:
            try:
                reply = generate_ai_reply(text)
                debug_info["reply"] = reply
                reply_thread = thread_ts if not is_dm else None
                
                # Inline post_slack_message to capture its response
                url = "https://slack.com/api/chat.postMessage"
                headers = {
                    "Authorization": f"Bearer {BOT_TOKEN}",
                    "Content-Type": "application/json; charset=utf-8"
                }
                payload = {"channel": channel, "text": reply}
                if reply_thread:
                    payload["thread_ts"] = reply_thread
                
                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
                try:
                    with urllib.request.urlopen(req) as res:
                        res_data = json.loads(res.read().decode("utf-8"))
                        debug_info["slack_api"] = res_data
                except Exception as ex:
                    debug_info["slack_error"] = str(ex)
                    
            except Exception as e:
                debug_info["error"] = str(e)

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "debug": debug_info}).encode())

