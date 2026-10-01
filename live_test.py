"""
Live integration test for Flezen SDK using provided credentials.
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from flezen import Flezen, FlezenAuthError, FlezenAPIError, FlezenUploadError

EMAIL = os.getenv("FLEZEN_EMAIL", "")
PASSWORD = os.getenv("FLEZEN_PASSWORD", "")

def run_live_test():
    if not EMAIL or not PASSWORD:
        print("[-] Please set FLEZEN_EMAIL and FLEZEN_PASSWORD environment variables to run live tests.")
        print("    Example: export FLEZEN_EMAIL='user@example.com' FLEZEN_PASSWORD='SecretPassword'")
        return

    print(f"[*] Attempting login with {EMAIL}...")

    try:
        client = Flezen(email=EMAIL, password=PASSWORD, auto_login=True)
        print("[+] Login successful!")
        print(f"    - fz cookie present: {bool(client.fz_token)}")
        print(f"    - rt cookie present: {bool(client.rt_token)}")
    except Exception as e:
        print(f"[-] Login failed: {e}")
        return

    # 1. Storage Usage
    print("\n[1] Checking storage usage...")
    try:
        usage = client.get_storage_usage()
        print(f"    Total storage used: {usage.total_storage_used} bytes")
        print(f"    Images: {usage.total_image_storage} bytes | Videos: {usage.total_video_storage} bytes")
    except Exception as e:
        print(f"    Error: {e}")

    # 2. List Files
    print("\n[2] Listing current files...")
    try:
        res = client.list_files(page=1)
        print(f"    Total files: {res.get('total', 0)}")
        for f in res.get("files", [])[:5]:
            print(f"    - {f.name} ({f.size} bytes, slug={f.slug})")
    except Exception as e:
        print(f"    Error: {e}")

    # 3. Create Sample File & Upload
    print("\n[3] Uploading sample file...")
    sample_path = "flezen_test_sample.txt"
    # Flezen requires Minimum File Size >= 1KB (1024 bytes)
    sample_content = (
        b"Flezen Python SDK Live Test - Verified Working\n"
        b"Hello from Python Flezen SDK client!\n" + (b"=" * 2048) + b"\nEnd of test payload.\n"
    )
    with open(sample_path, "wb") as f:
        f.write(sample_content)

    uploaded_file = None
    try:
        def progress(uploaded, total):
            pct = (uploaded / total) * 100 if total else 100
            print(f"    Uploading: {uploaded}/{total} bytes ({pct:.1f}%)")

        uploaded_file = client.upload_file(sample_path, custom_name="flezen_test_sample.txt", progress_callback=progress)
        print(f"[+] Upload complete!")
        print(f"    Name: {uploaded_file.name}")
        print(f"    Size: {uploaded_file.size} bytes")
        print(f"    Slug: {uploaded_file.slug}")
        print(f"    Public URL: {uploaded_file.public_url}")
        print(f"    Android Intent URL: {uploaded_file.intent_url}")
    except Exception as e:
        print(f"    Upload Error: {e}")
    finally:
        if os.path.exists(sample_path):
            os.remove(sample_path)

    # 4. Folder creation & file modification
    if uploaded_file:
        print("\n[4] Testing folder creation and file modification...")
        folder_id = ""
        try:
            folder_res = client.create_folder(name="SDK_Test_Folder")
            print(f"    Folder created: {folder_res}")
            folder_id = folder_res.get("id", "")
        except Exception as e:
            print(f"    Create folder error: {e}")

        try:
            mod_res = client.modify_file(slug=uploaded_file.slug, name="flezen_test_sample_updated.txt", visibility="public")
            print(f"    Modify file result: {mod_res}")
        except Exception as e:
            print(f"    Modify file error: {e}")

    # 5. Analytics & Stats
    print("\n[5] Fetching stats...")
    try:
        stats = client.get_stats("weekly")
        print(f"    Weekly stats: {stats}")
    except Exception as e:
        print(f"    Stats error: {e}")

    # 6. Traffic Sources
    print("\n[6] Fetching traffic sources...")
    try:
        sources = client.get_traffic_sources()
        print(f"    Traffic sources: {sources}")
    except Exception as e:
        print(f"    Traffic sources error: {e}")

    # 7. Notifications
    print("\n[7] Checking notifications...")
    try:
        count = client.get_unread_notifications_count()
        print(f"    Unread count: {count}")
        notifs = client.get_notifications()
        print(f"    Notifications received: {len(notifs) if isinstance(notifs, list) else notifs}")
    except Exception as e:
        print(f"    Notifications error: {e}")

    # 8. Support Tickets
    print("\n[8] Checking support tickets...")
    try:
        tickets = client.list_tickets(page=1)
        print(f"    Tickets: {tickets}")
    except Exception as e:
        print(f"    Tickets error: {e}")

    # 9. Payouts / Finance
    print("\n[9] Checking payment details & withdrawal history...")
    try:
        details = client.get_payment_details()
        print(f"    Payment details: {details}")
        history = client.get_withdrawal_history(page=1)
        print(f"    Withdrawal history: {history}")
    except Exception as e:
        print(f"    Payout error: {e}")

    print("\n================ LIVE TEST COMPLETE ================")

if __name__ == "__main__":
    run_live_test()
