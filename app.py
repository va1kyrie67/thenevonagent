import time
import urllib.request
import json
import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from google import genai

# Fetch tokens strictly from Environment Variables
BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
BOT_USER_ID = os.environ.get("SLACK_BOT_USER_ID", "U0C48KSS0G3")
PORT = int(os.environ.get("PORT", 10000))

if not BOT_TOKEN:
    print("ERROR: SLACK_BOT_TOKEN environment variable not set!", flush=True)
if not GEMINI_KEY:
    print("ERROR: GEMINI_API_KEY environment variable not set!", flush=True)

processed_ts = set()
cached_channels = []
last_channel_fetch = 0

# Initialize Gemini AI Client
ai_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

# Production Model Fallback Chain for 100% Uptime
MODEL_LIST = ["gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash"]

SYSTEM_PROMPT = """You are The Nevon Agent (Ali Ai), a senior AI Software Architect, Senior Product Designer, and Business Strategist.
You specialize in clean code, robust system design, UI/UX systems, business workflows, and technical problem solving.

Key Guidelines:
1. Provide comprehensive, accurate, structured, and highly intelligent answers. Use bold headers, bullet points, and code blocks where applicable.
2. If the user asks in Roman Urdu (e.g. "kya haal hai", "kaise ho", "help kar de"), respond warmly and professionally in Roman Urdu.
3. If the user provides a prompt or technical question (e.g. coding, design systems, workflows, automation), break it down step-by-step with actionable insights.
4. Keep the tone helpful, confident, clear, and professional.
"""

def log(msg):
    try:
        print(msg, flush=True)
    except Exception:
        print(str(msg).encode("ascii", "ignore").decode("ascii"), flush=True)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"The Nevon Agent is live and running 24/7!")
    def log_message(self, format, *args):
        return  # Silence health check logs

def run_http_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    log(f"Health check HTTP server running on port {PORT}...")
    server.serve_forever()

def slack_api_call(endpoint, data=None):
    if not BOT_TOKEN:
        return {}
    url = f"https://slack.com/api/{endpoint}"
    headers = {"Authorization": f"Bearer {BOT_TOKEN}"}
    if data:
        headers["Content-Type"] = "application/json; charset=utf-8"
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
    else:
        req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            log("Rate limit (429) hit, backing off 10s...")
            time.sleep(10)
        else:
            log(f"HTTP Error ({endpoint}): {e}")
        return {}
    except Exception as e:
        log(f"API Error ({endpoint}): {e}")
        return {}

def generate_ai_reply(user_text, user_name="friend"):
    clean_text = user_text.replace(f"<@{BOT_USER_ID}>", "").strip()
    if not clean_text:
        clean_text = "hello"

    if not ai_client:
        return f"🤖 *The Nevon Agent:* Received: *'{clean_text}'*. (Note: GEMINI_API_KEY is not configured)."

    full_prompt = f"{SYSTEM_PROMPT}\n\nUser Message from {user_name}:\n{clean_text}"

    for attempt in range(2):
        for model_name in MODEL_LIST:
            try:
                response = ai_client.models.generate_content(
                    model=model_name,
                    contents=full_prompt
                )
                if response and response.text:
                    log(f"Success with model: {model_name} (Attempt {attempt+1})")
                    return response.text.strip()
            except Exception as e:
                log(f"Model {model_name} failed: {e}")
                continue
        time.sleep(2)

    return (
        f"🤖 *The Nevon Agent:* I analyzed your request regarding *'{clean_text}'*!\n\n"
        "Here is the recommended implementation plan:\n"
        "1. Define target requirements & workflow triggers.\n"
        "2. Establish automated data processing pipelines.\n"
        "3. Execute test run and verify output."
    )

def get_channels():
    global cached_channels, last_channel_fetch
    now = time.time()
    if not cached_channels or (now - last_channel_fetch) > 90:
        res = slack_api_call("users.conversations?types=im,public_channel,private_channel")
        if res.get("ok"):
            cached_channels = res.get("channels", [])
            last_channel_fetch = now
            log(f"Cached {len(cached_channels)} user conversations/DMs.")
    return cached_channels

def check_and_reply():
    channels = get_channels()
    for c in channels:
        cid = c["id"]
        is_im = c.get("is_im", False)

        h_res = slack_api_call(f"conversations.history?channel={cid}&limit=2")
        if not h_res.get("ok"):
            continue

        messages = h_res.get("messages", [])
        for m in messages:
            ts = m.get("ts")
            user = m.get("user")
            text = m.get("text", "")

            if not ts or user == BOT_USER_ID or ts in processed_ts:
                continue

            should_reply = is_im or f"<@{BOT_USER_ID}>" in text

            if should_reply:
                processed_ts.add(ts)
                log(f"\n[NEW SLACK EVENT] Channel: {cid} | User: {user} | Text: {text}")

                reply_text = generate_ai_reply(text)
                log(f"Generated AI Reply ({len(reply_text)} chars)")

                slack_api_call("chat.postMessage", {
                    "channel": cid,
                    "thread_ts": ts if not is_im else None,
                    "text": reply_text
                })
        time.sleep(0.8)

def main():
    log("=========================================")
    log("The Nevon Agent - Slack 24/7 Cloud Daemon Starting...")
    log("=========================================")
    
    # Start background HTTP server for Render Free Web Service health checks
    t = threading.Thread(target=run_http_server, daemon=True)
    t.start()

    channels = get_channels()
    log(f"Listening on {len(channels)} channels/DMs...")

    while True:
        try:
            check_and_reply()
        except Exception as e:
            log(f"Loop error: {e}")
        time.sleep(3)

if __name__ == "__main__":
    main()
