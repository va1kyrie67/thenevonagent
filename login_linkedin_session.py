#!/usr/bin/env python3
"""
LinkedIn Session Authenticator for The Nevon Social Harvester
Supports 'Sign in with Google' and standard email/password login.
Saves session state to linkedin_session.json so Playwright can run headless.
"""

import os
import sys
import time
import argparse
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.path.join(BASE_DIR, "linkedin_session.json")

def login():
    print("=" * 60)
    print("      LinkedIn 1-Click Session Generator (Google Login Ready)")
    print("=" * 60)
    print(f"Target Output: {SESSION_FILE}\n")
    print("Launching Chrome browser...")

    with sync_playwright() as p:
        # Launch with stealth flags to allow 'Continue with Google'
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--start-maximized"
            ],
            ignore_default_args=["--enable-automation"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            no_viewport=True
        )
        page = context.new_page()

        # Remove webdriver flag
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        print("Navigating to LinkedIn Login page...")
        page.goto("https://www.linkedin.com/login", timeout=30000)

        print("\n" + "=" * 60)
        print(">>> ACTION REQUIRED IN THE OPEN BROWSER WINDOW:")
        print(">>> Click 'Continue with Google' or sign in with your burner account.")
        print(">>> Waiting up to 120 seconds for login to complete...")
        print("=" * 60 + "\n")

        logged_in = False
        start_time = time.time()
        timeout_seconds = 120

        while (time.time() - start_time) < timeout_seconds:
            cur_url = page.url
            cookies = context.cookies()
            has_li_at = any(c.get("name") == "li_at" for c in cookies)

            if ("/feed" in cur_url or "/in/" in cur_url or "/mynetwork" in cur_url or has_li_at) and "/login" not in cur_url:
                logged_in = True
                print(f"\n[SUCCESS] Detected active LinkedIn session! (URL: {cur_url})")
                break

            remaining = int(timeout_seconds - (time.time() - start_time))
            if remaining % 10 == 0:
                print(f"Waiting for login... ({remaining}s remaining)")
            time.sleep(2)

        if logged_in:
            print("Capturing authentication state & cookies...")
            time.sleep(3)
            context.storage_state(path=SESSION_FILE)
            print("\n" + "=" * 60)
            print(f"🎉 SUCCESS! Session saved permanently to:\n{SESSION_FILE}")
            print("Playwright can now browse LinkedIn headless without ever prompting for login again!")
            print("=" * 60 + "\n")
        else:
            print("\n[WARNING] Time expired before feed was reached.")
            # Check if any cookies exist anyway
            if context.cookies():
                context.storage_state(path=SESSION_FILE)
                print(f"Saved partial session to {SESSION_FILE}.")
            else:
                print("No cookies were captured.")

        browser.close()

if __name__ == "__main__":
    login()
