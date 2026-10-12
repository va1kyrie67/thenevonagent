#!/usr/bin/env python3
"""
Autonomous Social Media Harvester & Broadcaster for The Nevon Agent
Eliminates Chrome extension completely.
Fetches new posts for Nadir Bhai, Ali Aun, The Nevon, and CrushSVG across
LinkedIn, Facebook, and Instagram, and broadcasts formatted messages to Slack #social.
"""

import os
import sys
import json
import re
import time
import argparse
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "social_broadcast_history.json")
LINKEDIN_SESSION_FILE = os.path.join(BASE_DIR, "linkedin_session.json")

# Load local .env if present
def load_env_file():
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() not in os.environ:
                            os.environ[k.strip()] = v.strip()
        except Exception:
            pass

load_env_file()

BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("SLACK_SOCIAL_CHANNEL_ID", "C0B107Q0553")  # #social
ADMIN_USER_ID = os.environ.get("SLACK_ADMIN_USER_ID", "U0BDPLQ226R")   # Ali Aun

# Pakistan Timezone (PKT = UTC+5)
PKT = timezone(timedelta(hours=5))

def log(msg):
    now_str = datetime.now(PKT).strftime("%Y-%m-%d %H:%M:%S")
    try:
        print(f"[{now_str} PKT] {msg}", flush=True)
    except Exception:
        print(f"[{now_str} PKT] " + str(msg).encode("ascii", "replace").decode("ascii"), flush=True)

# -------------------------------------------------------------
# DEDUPLICATION & STATE MANAGEMENT
# -------------------------------------------------------------
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"Error loading history file: {e}")
    return {"posted_urls": [], "history": []}

def save_history(history_data):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history_data, f, indent=2)
    except Exception as e:
        log(f"Error saving history file: {e}")

def is_url_already_posted(url, history_data=None):
    if not history_data:
        history_data = load_history()
    clean = clean_social_url(url)
    
    # Check exact clean URL
    if clean in history_data.get("posted_urls", []):
        return True
    
    # Check normalized ID / permalink
    for posted in history_data.get("posted_urls", []):
        # Match Instagram shortcodes (/p/CODE/)
        m_curr = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', clean)
        m_prev = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', posted)
        if m_curr and m_prev and m_curr.group(1) == m_prev.group(1):
            return True
        # Match FB fbid
        fbid_curr = re.search(r'fbid=(\d+)', clean)
        fbid_prev = re.search(r'fbid=(\d+)', posted)
        if fbid_curr and fbid_prev and fbid_curr.group(1) == fbid_prev.group(1):
            return True
        # Match LinkedIn activity URN
        act_curr = re.search(r'activity[:-](\d+)', clean)
        act_prev = re.search(r'activity[:-](\d+)', posted)
        if act_curr and act_prev and act_curr.group(1) == act_prev.group(1):
            return True

    return False

def record_posted_url(url, brand, platform, history_data=None):
    if not history_data:
        history_data = load_history()
    clean = clean_social_url(url)
    if clean not in history_data["posted_urls"]:
        history_data["posted_urls"].append(clean)
    history_data["history"].append({
        "timestamp": datetime.now(PKT).strftime("%Y-%m-%d %H:%M:%S"),
        "brand": brand,
        "platform": platform,
        "url": clean
    })
    save_history(history_data)

# -------------------------------------------------------------
# URL CLEANING & FORMATTING (Exact Replica of Nevon Copy)
# -------------------------------------------------------------
def clean_social_url(url):
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        # Drop tracking params
        for p in ["trackingId", "ref", "utm_source", "utm_medium", "utm_campaign", "rcm"]:
            qs.pop(p, None)
        new_query = urllib.parse.urlencode(qs, doseq=True)
        cleaned = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, ""))
        return cleaned.rstrip("/")
    except Exception:
        return url.strip()

def detect_platform(url):
    lower = url.lower()
    if "facebook.com" in lower or "fb.me" in lower or "fb.watch" in lower:
        return "Facebook"
    if "instagram.com" in lower or "instagr.am" in lower:
        return "Insta"
    if "linkedin.com" in lower or "lnkd.in" in lower:
        return "Linkedin"
    return "Social"

def resolve_brand(url, brand_hint=None):
    if brand_hint and brand_hint != "auto":
        return brand_hint.lower()
    lower = url.lower()
    if "crushsvg" in lower or "61593405728605" in lower:
        return "crushsvg"
    if "ali-aun" in lower:
        return "ali"
    if "sardar-muhammad-nadir" in lower or "nadir" in lower or "nadir1214" in lower:
        return "nadir"
    if "thenevon" in lower or "the_nevon" in lower or "the-nevon" in lower or "61591527347235" in lower:
        return "thenevon"
    
    # Generic URLs / shortlinks: resolve by current PKT time window
    now = datetime.now(PKT)
    h = now.hour
    m = now.minute

    # 10:00 - 11:30 AM -> Nadir Bhai
    if (h == 10) or (h == 11 and m < 30):
        return "nadir"
    # 11:30 AM - 12:45 PM -> Ali Aun
    if (h == 11 and m >= 30) or (h == 12 and m < 45):
        return "ali"
    # 12:45 PM - 2:15 PM -> The Nevon
    if (h == 12 and m >= 45) or (h == 13) or (h == 14 and m < 15):
        return "thenevon"
    # 2:15 PM - 4:30 PM -> CrushSVG
    if (h == 14 and m >= 15) or (h == 15) or (h == 16 and m < 30):
        return "crushsvg"
    # 4:30 PM - 5:30 PM -> Nadir Bhai (2nd post)
    if (h == 16 and m >= 30) or (h == 17 and m < 30):
        return "nadir"
    # 5:30 PM - 8:00 PM -> Ali Aun (2nd post)
    if (h == 17 and m >= 30) or (h >= 18 and h <= 20):
        return "ali"

    return "thenevon"

def format_single_post(url, brand_hint=None):
    clean = clean_social_url(url)
    if not clean:
        return ""
    brand = resolve_brand(clean, brand_hint)
    platform = detect_platform(clean)

    if brand == "nadir":
        return f"Hey <!channel> ! must like and comment on this the post on Nadir bhai Linkedin Account.\n{clean}"
    
    if brand == "ali":
        return f"Hey <!channel> ! must like and comment on this post.\n{clean}"
    
    if brand == "crushsvg":
        if platform == "Insta":
            return f"Hey <!channel> ! must like the new post on CrushSVG Insta Page, y'all should follow the page and like the post and today we will be giving red tickets and penalty to anyone who have not been interacting with our recent post and they would have to work overtime.\n{clean}"
        elif platform == "Facebook":
            return f"Hey <!channel> ! must like the new post on CrushSVG Facebook Page, y'all should follow the page and like the post and today we will be giving red tickets and penalty to anyone who have not been interacting with our recent post and they would have to work overtime.\n{clean}"
        else:
            return f"Hey <!channel> ! must like the new post on CrushSVG Linkedin Page, and today we will be giving red tickets and penalty to anyone who have not been interacting with our recent post and they would have to work overtime.\n{clean}"

    # The Nevon Default
    if platform == "Insta":
        return f"Hey <!channel> ! must like this post on The Nevon instagram page, and today we will be giving red tickets and penalty to anyone who have not been interacting with our recent post and they would have to work overtime.\n{clean}"
    elif platform == "Facebook":
        return f"Hey <!channel> ! must like the new post on The Nevon Facebook Page, y'all should follow the page and like the post and today we will be giving red tickets and penalty to anyone who have not been interacting with our recent post and they would have to work overtime.\n{clean}"
    else:
        return f"Hey <!channel> ! must like the new post on The Nevon Linkedin Page, and today we will be giving red tickets and penalty to anyone who have not been interacting with our recent post and they would have to work overtime.\n{clean}"

def format_batch_posts(urls, brand_hint=None):
    blocks = []
    for u in urls:
        b = format_single_post(u, brand_hint)
        if b:
            blocks.append(b)
    return "\n\n".join(blocks)

# -------------------------------------------------------------
# SLACK BROADCASTER (Sends as 'The Nevon Agent')
# -------------------------------------------------------------
def post_to_slack_channel(text, channel_id=CHANNEL_ID):
    if not BOT_TOKEN:
        log("ERROR: SLACK_BOT_TOKEN not configured.")
        return False
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "channel": channel_id,
        "text": text
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode("utf-8"))
            if data.get("ok"):
                log(f"Successfully posted to Slack channel {channel_id}!")
                return True
            else:
                log(f"Slack API error: {data.get('error')}")
                return False
    except Exception as e:
        log(f"Failed to post to Slack: {e}")
        return False

def notify_admin_dm(brand_name, count=1):
    if not ADMIN_USER_ID or not BOT_TOKEN:
        return
    msg = f"📢 Successfully broadcasted *{brand_name}* ({count} post/s) to *#social*! ✨"
    post_to_slack_channel(msg, channel_id=ADMIN_USER_ID)

# -------------------------------------------------------------
# PLAYWRIGHT AUTONOMOUS HARVESTERS
# -------------------------------------------------------------
def harvest_instagram_profile(handle):
    """Fetches newest post/reel URL from an Instagram public handle without logging in."""
    from playwright.sync_api import sync_playwright
    url = f"https://www.instagram.com/{handle}/"
    log(f"Checking Instagram: {url}...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(url, timeout=25000)
            page.wait_for_timeout(3500)
            links = page.eval_on_selector_all('a', 'elements => elements.map(e => e.href)')
            browser.close()

            post_links = [l for l in links if '/p/' in l or '/reel/' in l]
            unique_links = list(dict.fromkeys(post_links))
            log(f"Found {len(unique_links)} post links on @{handle}")
            if unique_links:
                return unique_links[0]
    except Exception as e:
        log(f"Instagram harvest error for @{handle}: {e}")
    return None

def harvest_linkedin_activity(profile_or_company_url):
    """Fetches newest activity/post link from LinkedIn using saved session."""
    from playwright.sync_api import sync_playwright
    if not os.path.exists(LINKEDIN_SESSION_FILE):
        log(f"LinkedIn session file ({LINKEDIN_SESSION_FILE}) not found. Skipping automated LinkedIn fetch.")
        log("Run 'python login_linkedin_session.py' to authenticate LinkedIn once.")
        return None

    log(f"Checking LinkedIn: {profile_or_company_url}...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=LINKEDIN_SESSION_FILE,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(profile_or_company_url, timeout=30000)
            page.wait_for_timeout(4000)

            # Extract post links
            links = page.eval_on_selector_all('a', 'elements => elements.map(e => e.href)')
            browser.close()

            post_links = [l for l in links if 'activity-' in l or '/posts/' in l or 'urn:li:activity:' in l]
            unique_links = list(dict.fromkeys(post_links))
            log(f"Found {len(unique_links)} LinkedIn post links.")
            if unique_links:
                return unique_links[0]
    except Exception as e:
        log(f"LinkedIn harvest error: {e}")
    return None

def harvest_facebook_page(page_url):
    """Fetches newest photo/post link from public Facebook page."""
    from playwright.sync_api import sync_playwright
    log(f"Checking Facebook: {page_url}...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(page_url, timeout=25000)
            page.wait_for_timeout(4000)
            links = page.eval_on_selector_all('a', 'elements => elements.map(e => e.href)')
            browser.close()

            post_links = [l for l in links if 'photo/?fbid=' in l or '/posts/' in l]
            unique_links = list(dict.fromkeys(post_links))
            log(f"Found {len(unique_links)} Facebook post links.")
            if unique_links:
                return unique_links[0]
    except Exception as e:
        log(f"Facebook harvest error: {e}")
    return None

# -------------------------------------------------------------
# SLOT CONTROLLER & RUNNER
# -------------------------------------------------------------
def get_current_slot():
    now = datetime.now(PKT)
    h = now.hour
    m = now.minute

    # 10 AM (or 11 AM if late): Nadir Bhai Post 1
    if h == 10 or (h == 11 and m < 30):
        return "10am_nadir"
    # 12 PM: Ali Aun Post 1
    if h == 12 or (h == 11 and m >= 30):
        return "12pm_ali"
    # 1 PM: The Nevon Batch (LI, FB, Insta)
    if h == 13 or (h == 14 and m < 30):
        return "1pm_thenevon"
    # 3 PM: CrushSVG Batch (LI, FB, Insta)
    if h == 15 or (h == 16 and m < 30):
        return "3pm_crushsvg"
    # 5 PM: Nadir Bhai Post 2
    if h == 17:
        return "5pm_nadir"
    # 6 PM: Ali Aun Post 2
    if h == 18 or h == 19:
        return "6pm_ali"

    return "idle"

def execute_slot_harvest(slot_name):
    history = load_history()
    log(f"Executing harvest for slot: {slot_name}")
    new_posts_to_broadcast = []
    brand_label = ""

    if slot_name in ["10am_nadir", "5pm_nadir"]:
        brand_label = "Nadir Bhai"
        nadir_url = "https://www.linkedin.com/in/nadir1214/recent-activity/all/"
        link = harvest_linkedin_activity(nadir_url)
        if link and not is_url_already_posted(link, history):
            new_posts_to_broadcast.append(link)
            record_posted_url(link, "nadir", "Linkedin", history)

    elif slot_name in ["12pm_ali", "6pm_ali"]:
        brand_label = "Ali Aun"
        ali_url = "https://www.linkedin.com/in/ali-aun/recent-activity/all/"
        link = harvest_linkedin_activity(ali_url)
        if link and not is_url_already_posted(link, history):
            new_posts_to_broadcast.append(link)
            record_posted_url(link, "ali", "Linkedin", history)

    elif slot_name == "1pm_thenevon":
        brand_label = "The Nevon"
        # 1. Instagram (Usually live immediately)
        ig_link = harvest_instagram_profile("the_nevon")
        if ig_link and not is_url_already_posted(ig_link, history):
            new_posts_to_broadcast.append(ig_link)
            record_posted_url(ig_link, "thenevon", "Insta", history)

        # 2. Facebook
        fb_link = harvest_facebook_page("https://www.facebook.com/people/The-Nevon/61591527347235/")
        if fb_link and not is_url_already_posted(fb_link, history):
            new_posts_to_broadcast.append(fb_link)
            record_posted_url(fb_link, "thenevon", "Facebook", history)

        # 3. LinkedIn (May lag by 4-5 mins when scheduled)
        li_url = "https://www.linkedin.com/company/the-nevon/posts/"
        li_link = harvest_linkedin_activity(li_url)
        # If FB/Insta are found but LinkedIn is lagging, poll up to 5 times (waiting up to 4-5 mins)
        if not li_link and os.path.exists(LINKEDIN_SESSION_FILE):
            log("LinkedIn post not detected yet. Polling for up to 4 minutes to account for LinkedIn scheduling delay...")
            for attempt in range(5):
                time.sleep(45)
                li_link = harvest_linkedin_activity(li_url)
                if li_link and not is_url_already_posted(li_link, history):
                    log(f"LinkedIn post appeared after scheduling delay! Attempt {attempt+1}")
                    break

        if li_link and not is_url_already_posted(li_link, history):
            new_posts_to_broadcast.append(li_link)
            record_posted_url(li_link, "thenevon", "Linkedin", history)

    elif slot_name == "3pm_crushsvg":
        brand_label = "CrushSVG"
        # 1. Instagram
        ig_link = harvest_instagram_profile("crushsvg_net")
        if ig_link and not is_url_already_posted(ig_link, history):
            new_posts_to_broadcast.append(ig_link)
            record_posted_url(ig_link, "crushsvg", "Insta", history)

        # 2. Facebook
        fb_link = harvest_facebook_page("https://www.facebook.com/people/Crushsvg/61593405728605/")
        if fb_link and not is_url_already_posted(fb_link, history):
            new_posts_to_broadcast.append(fb_link)
            record_posted_url(fb_link, "crushsvg", "Facebook", history)

        # 3. LinkedIn (May lag by 4-5 mins when scheduled)
        li_url = "https://www.linkedin.com/company/crushsvg/posts/"
        li_link = harvest_linkedin_activity(li_url)
        if not li_link and os.path.exists(LINKEDIN_SESSION_FILE):
            log("LinkedIn post not detected yet. Polling for up to 4 minutes to account for LinkedIn scheduling delay...")
            for attempt in range(5):
                time.sleep(45)
                li_link = harvest_linkedin_activity(li_url)
                if li_link and not is_url_already_posted(li_link, history):
                    log(f"LinkedIn post appeared after scheduling delay! Attempt {attempt+1}")
                    break

        if li_link and not is_url_already_posted(li_link, history):
            new_posts_to_broadcast.append(li_link)
            record_posted_url(li_link, "crushsvg", "Linkedin", history)

    if new_posts_to_broadcast:
        log(f"Found {len(new_posts_to_broadcast)} NEW unposted link(s) for {brand_label}!")
        formatted_message = format_batch_posts(new_posts_to_broadcast)
        log("Generated Slack message block:\n" + formatted_message)
        
        ok = post_to_slack_channel(formatted_message)
        if ok:
            notify_admin_dm(brand_label, len(new_posts_to_broadcast))
        return True
    else:
        log(f"No new unposted links detected for {slot_name}. System is up to date.")
        return False

# -------------------------------------------------------------
# MAIN CLI
# -------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Autonomous Social Media Broadcaster")
    parser.add_argument("--slot", choices=["auto", "10am_nadir", "12pm_ali", "1pm_thenevon", "3pm_crushsvg", "5pm_nadir", "6pm_ali"], default="auto")
    parser.add_argument("--broadcast", help="Manual broadcast link(s) separated by spaces", nargs="+")
    parser.add_argument("--brand", choices=["auto", "nadir", "ali", "thenevon", "crushsvg"], default="auto")
    parser.add_argument("--test", choices=["instagram", "history", "format"], help="Run unit test")
    args = parser.parse_args()

    log("=== The Nevon Social Harvester & Broadcaster ===")

    # Manual Broadcast override
    if args.broadcast:
        urls = args.broadcast
        log(f"Manual broadcast requested for {len(urls)} link(s)...")
        formatted = format_batch_posts(urls, args.brand)
        print("\n" + formatted + "\n")
        ok = post_to_slack_channel(formatted)
        if ok:
            history = load_history()
            for u in urls:
                b = resolve_brand(u, args.brand)
                p = detect_platform(u)
                record_posted_url(u, b, p, history)
            notify_admin_dm(args.brand if args.brand != "auto" else "Manual", len(urls))
            log("Manual broadcast complete!")
        return

    # Tests
    if args.test == "format":
        test_urls = [
            "https://lnkd.in/p/dzVB7hd3",
            "https://www.instagram.com/p/DeT0bX5D6i3/?img_index=1",
            "https://www.facebook.com/photo/?fbid=122119391043446857&set=a.122107624713446857",
            "https://www.linkedin.com/posts/crushsvg_googleslides-pitchdeck-activity-7514625957979193345-c1Qm"
        ]
        print("\n--- TEST FORMATTING OUTPUT ---")
        print(format_batch_posts(test_urls))
        print("------------------------------\n")
        return

    if args.test == "instagram":
        print("Testing Instagram for the_nevon...")
        res1 = harvest_instagram_profile("the_nevon")
        print("the_nevon latest post:", res1)
        print("Testing Instagram for crushsvg_net...")
        res2 = harvest_instagram_profile("crushsvg_net")
        print("crushsvg_net latest post:", res2)
        return

    if args.test == "history":
        h = load_history()
        print(f"Total posted URLs tracked: {len(h.get('posted_urls', []))}")
        for item in h.get("history", [])[-5:]:
            print(" ", item)
        return

    # Slot execution
    slot = args.slot
    if slot == "auto":
        slot = get_current_slot()
        log(f"Auto-detected current slot: {slot}")

    if slot == "idle":
        log("Current time is outside active posting windows. Idle.")
        return

    execute_slot_harvest(slot)

if __name__ == "__main__":
    main()
