#!/usr/bin/env python3
"""
Test Suite for The Nevon Social Media Harvester & Broadcaster
Validates all templates against historical screenshots and live profiles.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from social_harvester import format_single_post, format_batch_posts, clean_social_url, resolve_brand, detect_platform

def test_nadir_post():
    url = "https://lnkd.in/p/dzVB7hd3"
    result = format_single_post(url, brand_hint="nadir")
    expected = (
        "Hey <!channel> ! must like and comment on this the post on Nadir bhai Linkedin Account.\n"
        "https://lnkd.in/p/dzVB7hd3"
    )
    assert result == expected, f"Nadir mismatch:\nGot: {result}\nExpected: {expected}"
    print("[PASS] Nadir Bhai 10 AM / 5 PM Template verified!")

def test_ali_post():
    url = "https://lnkd.in/p/dR3bB6Sh"
    result = format_single_post(url, brand_hint="ali")
    expected = (
        "Hey <!channel> ! must like and comment on this post.\n"
        "https://lnkd.in/p/dR3bB6Sh"
    )
    assert result == expected, f"Ali mismatch:\nGot: {result}\nExpected: {expected}"
    print("[PASS] Ali Aun 12 PM / 6 PM Template verified!")

def test_thenevon_batch():
    urls = [
        "https://www.facebook.com/photo/?fbid=122135220825384244&set=a.122114696325384244",
        "https://www.instagram.com/p/DeTmtm4DVx6/?img_index=1",
        "https://www.linkedin.com/posts/the-nevon_careergrowth-onboarding-newjob-activity-7514595603016757248-x3eH?utm_source=share&utm_medium=member_desktop&rcm=ACoAAG8zK-QBu6R1K8f0R8Xrv5n3-q_L-e109Oc"
    ]
    result = format_batch_posts(urls, brand_hint="thenevon")
    assert "Hey <!channel> ! must like the new post on The Nevon Facebook Page" in result
    assert "Hey <!channel> ! must like this post on The Nevon instagram page" in result
    assert "Hey <!channel> ! must like the new post on The Nevon Linkedin Page" in result
    assert "red tickets and penalty to anyone who have not been interacting" in result
    print("[PASS] The Nevon 1:00 PM Triple-Post Batch verified!")

def test_crushsvg_batch():
    urls = [
        "https://www.instagram.com/p/DeT0bX5D6i3/?img_index=1",
        "https://www.facebook.com/photo/?fbid=122119391043446857&set=a.122107624713446857",
        "https://www.linkedin.com/posts/crushsvg_googleslides-pitchdeck-svgtopng-activity-7514625957979193345-c1Qm?utm_source=share&utm_medium=member_desktop&rcm=ACoAAG8zK-QBu6R1K8f0R8Xrv5n3-q_L-e109Oc"
    ]
    result = format_batch_posts(urls, brand_hint="crushsvg")
    assert "Hey <!channel> ! must like the new post on CrushSVG Insta Page" in result
    assert "Hey <!channel> ! must like the new post on CrushSVG Facebook Page" in result
    assert "Hey <!channel> ! must like the new post on CrushSVG Linkedin Page" in result
    assert "red tickets and penalty to anyone who have not been interacting" in result
    print("[PASS] CrushSVG 3:00 PM Triple-Post Batch verified!")

def test_clean_tracking():
    dirty = "https://www.linkedin.com/posts/crushsvg_activity?utm_source=share&utm_medium=desktop&ref=test&rcm=123"
    cleaned = clean_social_url(dirty)
    assert "utm_source" not in cleaned
    assert "rcm" not in cleaned
    assert "ref" not in cleaned
    print("[PASS] URL tracking parameter sanitization verified!")

def test_new_user_urls():
    # Nadir 1214
    nadir_res = format_single_post("https://www.linkedin.com/in/nadir1214/posts/test")
    assert "Nadir bhai Linkedin Account" in nadir_res

    # The Nevon FB ID 61591527347235
    nevon_fb = format_single_post("https://www.facebook.com/photo/?fbid=122135732043384244&id=61591527347235")
    assert "The Nevon Facebook Page" in nevon_fb

    # CrushSVG FB ID 61593405728605
    crush_fb = format_single_post("https://www.facebook.com/photo/?fbid=122119859937446857&id=61593405728605")
    assert "CrushSVG Facebook Page" in crush_fb

    # The Nevon LinkedIn company slug
    nevon_li = format_single_post("https://www.linkedin.com/company/the-nevon/posts/")
    assert "The Nevon Linkedin Page" in nevon_li
    print("[PASS] User-confirmed brand profile URLs verified!")

if __name__ == "__main__":
    print("Running Social Media Broadcaster Test Suite...")
    test_nadir_post()
    test_ali_post()
    test_thenevon_batch()
    test_crushsvg_batch()
    test_clean_tracking()
    test_new_user_urls()
    print("\nALL 6 TEST SUITES PASSED 100% PERFECTLY!")
