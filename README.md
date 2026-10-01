# Flezen Python SDK

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Official-grade, full-featured Python client SDK for [Flezen](https://flezen.com), implementing the reverse-engineered API specification with live verification.

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Authentication](#authentication)
- [Uploading Files & Tracking Progress](#uploading-files--tracking-progress)
- [Public Links & Android Intent Deep Links](#public-links--android-intent-deep-links)
- [File & Storage Management](#file--storage-management)
- [Analytics & Monetization](#analytics--monetization)
- [Payouts & Finance](#payouts--finance)
- [Notifications & Support Tickets](#notifications--support-tickets)
- [Account Security & Revocation](#account-security--revocation)
- [Error Handling](#error-handling)
- [API Reference](#api-reference)
- [Running Unit Tests](#running-unit-tests)
- [License](#license)

---

## Features

- **Authentication**: Email/password authentication, automatic cookie management (`fz` access JWT, `rt` refresh UUID), and Telegram Bot API key support.
- **Chunked Multi-Part Upload Engine**: Robust 3-step file and byte streaming uploads directly to Flezen regional edge storage nodes, with **real-time socket progress tracking**.
- **File & Storage Management**: List files with pagination, sorting (`name`, `time`, `size`, `views`), search query, folder creation, moving, renaming, public/private visibility toggles, cloning, and deletion.
- **Mobile Gatekeeper & Link Utilities**: Generate public share URLs (`/s/{slug}`) and Android Intent deep links (`intent://...`).
- **Analytics & Monetization**: Retrieve daily, weekly, or monthly earnings & views stats, and whitelist approved traffic sources (e.g. Telegram channels).
- **Payouts & Finance**: Configure UPI, PayPal, or Bank payout details, submit withdrawal requests, and query transaction history.
- **Support Tickets & Notifications**: Fetch unread counts, list and mark notifications as read, open tickets, and view ticket threads.
- **Account Security**: Session revocation, bot key revocation, password changes, and 3-step OTP-based account deletion.

---

## Installation

```bash
git clone https://github.com/your-username/Flezen.git
cd Flezen
pip install -e .
```

Or install the single required dependency:

```bash
pip install requests
```

---

## Quickstart

```python
from flezen import Flezen

# Initialize client and log in
with Flezen(email="user@example.com", password="YourPassword123") as client:
    # 1. Check storage usage
    usage = client.get_storage_usage()
    print(f"Total storage used: {usage.total_storage_used:,} bytes")

    # 2. Upload a file with progress tracking
    file = client.upload_file(
        "photo.png", 
        progress_callback=lambda up, total: print(f"\rUploading: {up:,}/{total:,} bytes", end="")
    )
    print(f"\nUploaded! Public URL: {file.public_url}")

    # 3. List recent files
    res = client.list_files(sort_by="time", sort_order="desc")
    for f in res["files"]:
        print(f"- {f.name} (views: {f.views}, slug: {f.slug})")
```

---

## Authentication

### Option A: Email & Password (Recommended)
Automatically logs in and stores `fz` (15-min access token) and `rt` (30-day refresh token) cookies:

```python
client = Flezen(email="user@example.com", password="YourPassword123")
```

### Option B: Use as Context Manager
Ensures the underlying HTTP session connection pool is properly closed:

```python
with Flezen(email="user@example.com", password="YourPassword123") as client:
    # Operations here
    pass
```

### Option C: Existing Session Cookies
If you already extracted your `fz` and `rt` cookies:

```python
client = Flezen(fz="<access_jwt>", rt="<refresh_uuid>")
```

### Option D: Bot API Key
```python
client = Flezen(api_key="<your_bot_api_key_uuid>")
```

---

## Uploading Files & Tracking Progress

Flezen uses a **3-step chunked upload engine** (`/user/upload/initiate` $\rightarrow$ `PUT {serverUrl}/?x={signedID}` $\rightarrow$ `/user/upload/complete`).

> [!NOTE]
> Flezen enforces a **Minimum File Size of 1 KB (1,024 bytes)** on the upload endpoint.

### 1. Upload Local File with Interactive Progress Bar

```python
import sys
from flezen import Flezen

def progress_bar(uploaded: int, total: int):
    pct = (uploaded / total) * 100
    bar_width = 30
    filled = int(bar_width * uploaded // total)
    bar = "=" * filled + "-" * (bar_width - filled)
    sys.stdout.write(f"\r[{bar}] {uploaded:,}/{total:,} bytes ({pct:.1f}%)")
    sys.stdout.flush()

with Flezen(email="user@example.com", password="YourPassword123") as client:
    file = client.upload_file(
        file_path="movie.mp4",
        custom_name="my_movie.mp4",        # Optional custom name
        parent_id="",                       # Optional target folder slug
        progress_callback=progress_bar      # Live socket streaming callback
    )
    print(f"\nUpload complete: {file.public_url}")
```

### 2. Upload Directly from In-Memory Bytes

```python
data = b"Testing in-memory uploads! " + (b"X" * 2048)  # Must be >= 1024 bytes

file = client.upload_bytes(
    data=data,
    filename="in_memory_file.txt",
    progress_callback=lambda u, t: print(f"{u}/{t} bytes")
)
print("Uploaded slug:", file.slug)
```

### 3. Upload Directly from a Public URL

Stream remote files directly from any HTTP/HTTPS URL into Flezen edge storage without downloading the entire file to disk first or consuming high RAM:

```python
url = "https://example.com/files/sample_video.mp4"

file = client.upload_from_url(
    url=url,
    custom_name="my_downloaded_video.mp4",  # Optional, auto-extracted if omitted
    progress_callback=lambda u, t: print(f"Streaming upload: {u}/{t} bytes")
)
print("Upload Complete! Public Link:", file.public_url)
```

---


## Public Links & Android Intent Deep Links

Flezen monetizes content by redirecting downloads to their Android application. The SDK provides helper properties and static methods to generate both formats:

```python
slug = file.slug  # e.g. "datshcpbjlnn744eui0gtsvtde-6f18"

# Public Web URL
print(file.public_url)
# Output: https://flezen.com/s/datshcpbjlnn744eui0gtsvtde-6f18

# Android Intent Deep Link
print(file.intent_url)
# Output: intent://flezen.com/s/...#Intent;scheme=flezen;package=com.devlooper.flezen;...

# Or use static helper methods
public_url = Flezen.get_public_url(slug)
intent_url = Flezen.get_intent_url(slug)
app_url = Flezen.get_app_url(slug)
```

---

## File & Storage Management

```python
# 1. Storage Usage Breakdown
usage = client.get_storage_usage()
print(f"Total:  {usage.total_storage_used:,} bytes")
print(f"Images: {usage.total_image_storage:,} bytes")
print(f"Videos: {usage.total_video_storage:,} bytes")

# 2. List Files (with pagination and sorting)
res = client.list_files(
    page=1,
    sort_by="time",       # 'name', 'time', 'size', 'views'
    sort_order="desc",    # 'asc', 'desc'
    query="photo"         # Optional search term
)
for f in res["files"]:
    print(f"{f.name} ({f.size} bytes) - Views: {f.views}")

# 3. Create a Folder
folder = client.create_folder(name="Wallpapers")
folder_slug = folder["slug"]

# 4. Move File to Folder
client.move_file(slug=file.slug, parent_id=folder_slug)

# 5. Rename or Change Visibility ('public' or 'private')
client.modify_file(slug=file.slug, name="renamed.png", visibility="private")

# 6. Duplicate / Clone File
client.copy_file(slug=file.slug)

# 7. Delete File or Folder
client.delete_file(slug=file.slug)
```

---

## Analytics & Monetization

```python
# Fetch earnings and views stats ('weekly', 'monthly', or 'daily')
stats = client.get_stats(period="weekly")
print("Total earnings breakdown:", stats["total_earnings"])
print("Total views breakdown:   ", stats["total_views"])

# Manage traffic sources whitelist (e.g. Telegram channel links)
sources = client.get_traffic_sources()
client.add_traffic_source("https://t.me/my_channel")
client.remove_traffic_source("https://t.me/my_channel")
```

---

## Payouts & Finance

```python
# 1. Configure UPI ($5.00 min - $60.00 max)
client.set_payment_upi(name="Full Name", upi_id="user@okhdfcbank")

# 2. Configure PayPal (balances > $60.00)
client.set_payment_paypal(name="Full Name", email="user@example.com")

# 3. Configure Direct Bank Transfer (1: Savings, 2: Current, 3: NRE)
client.set_payment_bank(
    name="Full Name",
    account="1234567890",
    ifsc="SBIN0001",
    account_type=1
)

# 4. Inspect Saved Payment Methods
details = client.get_payment_details()

# 5. Submit Withdrawal Request ('upi', 'paypal', or 'bank')
client.request_withdrawal(method="upi")

# 6. Get Withdrawal Transaction History
history = client.get_withdrawal_history(page=1)
```

---

## Notifications & Support Tickets

```python
# Check Unread Count
unread_count = client.get_unread_notifications_count()

# List Notifications & Mark As Read (0 marks all read)
notifs = client.get_notifications()
client.mark_notification_as_read(notification_id=0)

# Open Support Ticket
client.create_ticket(subject="Withdrawal inquiry", body="My question is...")

# List Tickets & View Thread Messages
tickets = client.list_tickets(page=1)
thread = client.get_ticket(ticket_id=101)
```

---

## Account Security & Revocation

```python
# Revoke a specific active session
client.revoke_session(session_id="session_string_id")

# Revoke all other logged-in sessions
client.revoke_all_sessions()

# Revoke Telegram Bot Key
client.revoke_bot_key()

# Change Account Password
client.change_password(old_password="OldPassword123", new_password="NewPassword456")

# 3-Step Account Deletion (Email OTP based)
# Step 1: Send OTP to account email
client.delete_account_request(password="CurrentPassword")
# Step 2: (Optional) Resend OTP
client.delete_account_resend_otp()
# Step 3: Confirm deletion
client.delete_account_confirm(otp="123456")
```

---

## Error Handling

The SDK provides explicit exception classes:

```python
from flezen.exceptions import (
    FlezenError,
    FlezenAuthError,
    FlezenAPIError,
    FlezenUploadError,
)

try:
    with Flezen(email="user@example.com", password="Password123") as client:
        file = client.upload_file("data.bin")
except FlezenAuthError as e:
    print(f"Authentication failed: {e}")
except FlezenUploadError as e:
    print(f"Upload failed at chunk or complete step: {e}")
except FlezenAPIError as e:
    print(f"API request failed with HTTP {e.status_code}: {e.response_text}")
except FlezenError as e:
    print(f"General SDK error: {e}")
```

---

## API Reference

| Category | Method | Description |
| :--- | :--- | :--- |
| **Auth** | `login(email, password)` | Log in and set `fz` & `rt` cookies |
| | `register(email, password, ref)` | Register a new account |
| | `forgot_password(email)` | Trigger password reset verification email |
| | `logout()` | Invalidate current session and clear cookies |
| **Uploads** | `upload_file(path, ...)` | 3-step chunked file upload with progress tracking |
| | `upload_bytes(data, ...)` | 3-step chunked in-memory upload with progress tracking |
| | `upload_from_url(url, ...)` | Direct URL streaming upload to Flezen storage with progress tracking |
| **Files** | `list_files(page, sort_by, query)` | List and filter uploaded files |
| | `get_storage_usage()` | Get categorized storage consumption |
| | `create_folder(name, parent_id)` | Create directory in storage |
| | `move_file(slug, parent_id)` | Move file into a directory |
| | `modify_file(slug, name, visibility)` | Rename or toggle `public`/`private` |
| | `delete_file(slug)` | Permanently delete file or directory |
| | `copy_file(slug)` | Server-side file clone/duplication |
| **Links** | `get_public_url(slug)` | Generate `https://flezen.com/s/{slug}` |
| | `get_intent_url(slug)` | Generate Android Intent deep link |
| | `get_app_url(slug)` | Generate `flezen://flezen.com/s/{slug}` |
| **Analytics** | `get_stats(period)` | Fetch stats for `weekly`, `monthly`, or `daily` |
| | `get_traffic_sources()` | Get approved traffic channels |
| | `add_traffic_source(link)` | Add channel link to whitelist |
| | `remove_traffic_source(link)` | Remove channel link from whitelist |
| **Payouts** | `set_payment_upi(name, upi_id)` | Save UPI payout configuration |
| | `set_payment_paypal(name, email)` | Save PayPal payout configuration |
| | `set_payment_bank(name, acc, ifsc)` | Save Direct Bank transfer configuration |
| | `request_withdrawal(method)` | Submit withdrawal (`upi`, `paypal`, `bank`) |
| | `get_withdrawal_history(page)` | List past withdrawal requests |
| **Tickets** | `list_tickets(page)` | List support tickets |
| | `create_ticket(subject, body)` | Open new support ticket |
| | `get_ticket(id)` | View ticket messages and thread |
| **Security** | `revoke_session(session_id)` | Invalidate a specific active session |
| | `revoke_all_sessions()` | Invalidate all sessions except current |
| | `revoke_bot_key()` | Regenerate Telegram Bot API key |
| | `change_password(...)` | Change account password |
| | `delete_account_confirm(otp)` | Confirm deletion using 6-digit email OTP |

---

## Running Unit Tests

Run the complete test suite:

```bash
python3 -m unittest discover tests
```

---

## License

This project is licensed under the MIT License.
