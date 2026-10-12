#!/usr/bin/env python3
"""
LinkedIn Session Authenticator for The Nevon Social Harvester
Logs into LinkedIn once and saves cookies/tokens to linkedin_session.json.
Playwright can then run completely headless without credentials or authwalls.
"""

import os
import sys
import time
import argparse
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.path.join(BASE_DIR, "linkedin_session.json")

def login(email=None, password=None):
    print("==================================================")
    print("      LinkedIn Session Generator for Playwright   ")
    print("==================================================")
    print(f"Target Session Output: {SESSION_FILE}\n")

    with sync_playwright() as p:
        # Launch browser headfully so user can solve CAPTCHA or confirm if needed
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("Opening LinkedIn login page...")
        page.goto("https://www.linkedin.com/login", timeout=30000)
        page.wait_for_timeout(2000)

        if email and password:
            print(f"Filling credentials for: {email}...")
            page.fill('input#username', email)
            page.fill('input#password', password)
            page.click('button[type="submit"]')
            print("Credentials submitted. Waiting for feed...")

        print("\n>>> Please complete login in the browser window if prompted (or if CAPTCHA appears)...")
        print(">>> Waiting up to 60 seconds for successful login into LinkedIn feed...")

        # Wait until user reaches feed or check cookies
        logged_in = False
        for i in range(30):
            time.sleep(2)
            cur_url = page.url
            if "/feed" in cur_url or "/mynetwork" in cur_url or "/in/" in cur_url:
                logged_in = True
                print(f"\n[SUCCESS] Detected logged-in URL: {cur_url}")
                break

        if logged_in:
            page.wait_for_timeout(3000)
            context.storage_state(path=SESSION_FILE)
            print(f"\n[SUCCESS] LinkedIn session state saved permanently to:\n{SESSION_FILE}")
            print("Playwright can now browse LinkedIn headless without ever prompting for login again!\n")
        else:
            print("\n[WARNING] Could not confirm feed within 60s. Checking if cookies exist...")
            context.storage_state(path=SESSION_FILE)
            print(f"Session saved to {SESSION_FILE}. You can test with: python social_harvester.py --slot=10am_nadir")

        browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LinkedIn Session Authenticator")
    parser.add_argument("--email", help="LinkedIn Email", default=None)
    parser.add_argument("--password", help="LinkedIn Password", default=None)
    args = parser.parse_args()

    login(args.email, args.password)
