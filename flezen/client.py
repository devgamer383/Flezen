"""
Flezen API Python Client
Official-grade SDK for flezen.com
"""

import io
import math
import os
import re
from pathlib import Path
from typing import Any, BinaryIO, Callable, Dict, List, Optional, Union
from urllib.parse import unquote, urljoin, urlparse

import requests


from .exceptions import (
    FlezenAPIError,
    FlezenAuthError,
    FlezenError,
    FlezenUploadError,
)
from .models import FlezenFile, StorageUsage, UploadInitResponse


class _ProgressStream(io.BytesIO):
    """BytesIO wrapper that calls a callback as bytes are read by requests."""
    def __init__(self, data: bytes, on_read: Optional[Callable[[int], None]] = None):
        super().__init__(data)
        self.on_read = on_read

    def read(self, size: int = -1) -> bytes:
        chunk = super().read(size)
        if self.on_read and chunk:
            self.on_read(len(chunk))
        return chunk


def _extract_filename_from_url(url: str, response: Optional[requests.Response] = None) -> str:
    """Extract a filename from Content-Disposition header or the URL path."""
    if response and "Content-Disposition" in response.headers:
        cd = response.headers["Content-Disposition"]
        matches = re.findall(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', cd, re.IGNORECASE)
        if matches:
            return unquote(matches[0].strip().strip('"\''))

    parsed = urlparse(url)
    basename = os.path.basename(unquote(parsed.path))
    if basename:
        return basename
    return "downloaded_file"



class Flezen:
    """
    Python client for Flezen (https://flezen.com).
    
    Supports authentication, chunked multi-part file uploads, folder & file management,
    analytics, payment settings, support tickets, notifications, and security controls.
    """

    DEFAULT_BASE_URL = "https://flezen.com"
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        fz: Optional[str] = None,
        rt: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        session: Optional[requests.Session] = None,
        timeout: int = 60,
        auto_login: bool = True,
    ):
        """
        Initialize the Flezen client.

        :param email: Account email for credentials-based login.
        :param password: Account password for credentials-based login.
        :param fz: Optional existing access token JWT cookie ('fz').
        :param rt: Optional existing refresh token UUID cookie ('rt').
        :param api_key: Optional Bot API Key (from /user/bots).
        :param base_url: Base URL of Flezen (default: 'https://flezen.com').
        :param session: Optional pre-configured requests.Session.
        :param timeout: Request timeout in seconds.
        :param auto_login: If True and email/password provided, log in immediately.
        """
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.api_key = api_key
        self.timeout = timeout

        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": self.DEFAULT_USER_AGENT,
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://flezen.com/",
            "Origin": "https://flezen.com",
        })

        if api_key:
            self.session.headers["X-API-Key"] = api_key

        if fz:

            self.session.cookies.set("fz", fz, domain=".flezen.com")
            self.session.cookies.set("fz", fz, domain="flezen.com")
        if rt:
            self.session.cookies.set("rt", rt, domain=".flezen.com")
            self.session.cookies.set("rt", rt, domain="flezen.com")

        if auto_login and self.email and self.password and not (fz or rt):
            self.login()

    def __enter__(self) -> "Flezen":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close the underlying HTTP session."""
        self.session.close()

    @property
    def is_authenticated(self) -> bool:
        """Check if an access token 'fz' or refresh token 'rt' is present in cookies."""
        return bool(
            self.session.cookies.get("fz") or self.session.cookies.get("rt")
        )

    @property
    def fz_token(self) -> Optional[str]:
        """Return the current 'fz' JWT access token from session cookies."""
        return self.session.cookies.get("fz")

    @property
    def rt_token(self) -> Optional[str]:
        """Return the current 'rt' refresh token from session cookies."""
        return self.session.cookies.get("rt")

    # =========================================================================
    # URL Helpers
    # =========================================================================

    @staticmethod
    def get_public_url(slug: str) -> str:
        """
        Get public file URL.
        Example: https://flezen.com/s/{slug}
        """
        return f"https://flezen.com/s/{slug}"

    @staticmethod
    def get_intent_url(slug: str) -> str:
        """
        Get Android Intent deep link URL.
        """
        return (
            f"intent://flezen.com/s/{slug}#Intent;"
            f"scheme=flezen;package=com.devlooper.flezen;"
            f"S.browser_fallback_url=https://play.google.com/store/apps/details?id=com.devlooper.flezen;end"
        )

    @staticmethod
    def get_app_url(slug: str) -> str:
        """
        Get custom flezen app scheme URL.
        Example: flezen://flezen.com/s/{slug}
        """
        return f"flezen://flezen.com/s/{slug}"

    # =========================================================================
    # HTTP Internal Request Helpers
    # =========================================================================

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        allow_redirects: bool = True,
        is_upload: bool = False,
    ) -> requests.Response:
        """Centralized HTTP request handler with status checking and error mapping."""
        url = endpoint if endpoint.startswith("http") else urljoin(self.base_url + "/", endpoint.lstrip("/"))
        
        req_headers = {}
        if headers:
            req_headers.update(headers)

        response = None
        for attempt in range(2):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    json=json,
                    headers=req_headers,
                    timeout=self.timeout,
                    allow_redirects=allow_redirects,
                )
                break
            except (requests.ConnectionError, requests.Timeout) as e:
                # Stale keep-alive socket or transient connection reset - retry on fresh socket
                if attempt == 0:
                    continue
                raise FlezenError(f"HTTP connection error: {e}") from e
            except requests.RequestException as e:
                raise FlezenError(f"HTTP connection error: {e}") from e


        # Handle unauthorized / redirect to login
        if response.status_code == 401 or (
            response.history and any(r.status_code in (302, 303) and "/auth/login" in r.headers.get("Location", "") for r in response.history)
        ):
            # Attempt re-login if credentials available
            if self.email and self.password and not endpoint.startswith("/auth/login"):
                self.login()
                # Retry once
                return self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    json=json,
                    headers=req_headers,
                    timeout=self.timeout,
                    allow_redirects=allow_redirects,
                )
            raise FlezenAuthError("Unauthorized: Session is invalid or expired.")

        if not response.ok and response.status_code not in (302, 303):
            err_msg = f"Request to {endpoint} failed with status {response.status_code}"
            try:
                err_data = response.json()
                if isinstance(err_data, dict) and "message" in err_data:
                    err_msg = f"{err_msg}: {err_data['message']}"
                elif isinstance(err_data, dict) and "error" in err_data:
                    err_msg = f"{err_msg}: {err_data['error']}"
            except Exception:
                pass
            raise FlezenAPIError(err_msg, status_code=response.status_code, response_text=response.text)

        return response

    # =========================================================================
    # 1. Authentication Endpoints
    # =========================================================================

    def login(self, email: Optional[str] = None, password: Optional[str] = None) -> bool:
        """
        Log in using email and password.
        Sets 'fz' and 'rt' session cookies on success.
        
        :param email: User email (defaults to instance email).
        :param password: User password (defaults to instance password).
        :return: True if login succeeded.
        :raises FlezenAuthError: If credentials are invalid.
        """
        login_email = email or self.email
        login_password = password or self.password

        if not login_email or not login_password:
            raise FlezenAuthError("Both email and password are required for login.")

        endpoint = "/auth/login"
        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        
        res = self.session.post(
            url,
            data={"email": login_email, "password": login_password},
            timeout=self.timeout,
            allow_redirects=False,
        )

        # Successful login returns 302/303 redirect to /user/dashboard
        if res.status_code in (302, 303):
            loc = res.headers.get("Location", "")
            if "/user/dashboard" in loc or "dashboard" in loc or "fz" in self.session.cookies:
                self.email = login_email
                self.password = login_password
                return True

        # Check for cookies even if redirect was 200 or followed
        if "fz" in self.session.cookies or "rt" in self.session.cookies:
            self.email = login_email
            self.password = login_password
            return True

        # Extract error message if present in DOM
        error_msg = "Invalid email or password"
        if res.text:
            match = re.search(r'id=["\'](?:email-error|password-error)["\'][^>]*>(.*?)<', res.text, re.DOTALL)
            if match:
                error_msg = match.group(1).strip()
            elif "Invalid email or password" in res.text:
                error_msg = "Invalid email or password"

        raise FlezenAuthError(f"Login failed: {error_msg}")

    def register(
        self,
        email: str,
        password: str,
        confirm_password: Optional[str] = None,
        ref: Optional[str] = None,
    ) -> bool:
        """
        Register a new Flezen account.
        
        :param email: Account email.
        :param password: Account password.
        :param confirm_password: Password confirmation (defaults to password).
        :param ref: Optional affiliate referral code.
        :return: True if registration succeeded.
        """
        params = {"ref": ref} if ref else None
        data = {
            "email": email,
            "password": password,
            "confirm_password": confirm_password or password,
        }
        res = self.session.post(
            urljoin(self.base_url + "/", "auth/register"),
            params=params,
            data=data,
            timeout=self.timeout,
            allow_redirects=False,
        )
        if res.status_code in (302, 303) or "fz" in self.session.cookies:
            self.email = email
            self.password = password
            return True

        raise FlezenAuthError("Registration failed. Please verify credentials or email availability.")

    def forgot_password(self, email: str) -> Dict[str, Any]:
        """
        Request a password reset link/token.
        """
        res = self._request("POST", "/auth/forgot-password", data={"email": email})
        try:
            return res.json()
        except Exception:
            return {"success": True, "message": "Password reset email sent if the account exists."}

    def logout(self) -> bool:
        """
        Log out and invalidate current cookies.
        """
        self._request("GET", "/auth/logout", allow_redirects=True)
        self.session.cookies.clear()
        return True

    # =========================================================================
    # 4. Chunked Multi-Part File Upload Engine
    # =========================================================================

    def initiate_upload(
        self,
        name: str,
        size: int,
        parent_id: str = "",
    ) -> UploadInitResponse:
        """
        Step 1: Initiate an upload session.

        :param name: File name (e.g. 'photo.png').
        :param size: Total file size in bytes.
        :param parent_id: Optional parent folder ID.
        :return: UploadInitResponse containing signature, signedIDs, partSize, serverUrl.
        """
        res = self._request(
            "POST",
            "/user/upload/initiate",
            json={"name": name, "size": size, "parent_id": parent_id},
        )
        data = res.json()
        return UploadInitResponse.from_dict(data)

    def upload_chunk(
        self,
        server_url: str,
        signed_id: str,
        chunk_data: bytes,
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> str:
        """
        Step 2: Upload a binary slice to the regional edge storage node.

        :param server_url: Storage server URL (from initiate_upload).
        :param signed_id: Part signed ID token.
        :param chunk_data: Raw byte slice.
        :param on_progress: Optional callback fn(bytes_read) called during chunk streaming.
        :return: The internal part ID (jId).
        """
        url = f"{server_url.rstrip('/')}/?x={signed_id}"
        headers = {
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(chunk_data)),
        }
        stream = _ProgressStream(chunk_data, on_read=on_progress) if on_progress else chunk_data
        try:
            res = self.session.put(
                url,
                data=stream,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise FlezenUploadError(f"Chunk upload failed to {url}: {e}") from e

        if not res.ok:
            raise FlezenUploadError(
                f"Chunk upload failed with status {res.status_code}: {res.text}"
            )

        try:
            data = res.json()
            return data["jId"]
        except Exception as e:
            raise FlezenUploadError(f"Invalid chunk response format: {res.text}") from e

    def complete_upload(
        self,
        signature_id: str,
        parts: List[Dict[str, Any]],
    ) -> FlezenFile:
        """
        Step 3: Complete & finalize the upload session.

        :param signature_id: Upload signature UUID.
        :param parts: List of part dicts, e.g. [{"number": 1, "id": "part_internal_id"}].
        :return: FlezenFile representing the uploaded file.
        """
        res = self._request(
            "POST",
            "/user/upload/complete",
            json={"signature_id": signature_id, "parts": parts},
        )
        data = res.json()
        is_success = bool(data.get("success") or data.get("sucess") or ("slug" in data))
        if not is_success:
            raise FlezenUploadError(f"Finalize upload failed: {data}")

        file_data = data.get("file") if isinstance(data.get("file"), dict) else data
        return FlezenFile.from_dict(file_data)


    def upload_file(
        self,
        file_path: Union[str, Path],
        parent_id: str = "",
        custom_name: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> FlezenFile:
        """
        High-level helper to upload a local file using the 3-step chunked engine.

        :param file_path: Path to the local file.
        :param parent_id: Optional parent folder ID.
        :param custom_name: Optional custom filename to store as.
        :param progress_callback: Optional callback fn(uploaded_bytes, total_bytes).
        :return: FlezenFile metadata.
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_name = custom_name or path.name
        file_size = path.stat().st_size

        init_res = self.initiate_upload(name=file_name, size=file_size, parent_id=parent_id)

        part_size = init_res.part_size
        total_parts = max(1, math.ceil(file_size / part_size))
        signed_ids = init_res.signed_ids

        uploaded_parts = []
        bytes_transferred = 0

        with open(path, "rb") as f:
            for part_num in range(1, total_parts + 1):
                chunk = f.read(part_size)
                if not chunk and part_num > 1:
                    break

                signed_id_index = part_num - 1
                if signed_id_index < len(signed_ids):
                    signed_id = signed_ids[signed_id_index]
                else:
                    signed_id = signed_ids[-1]

                def on_chunk_bytes(bytes_read: int):
                    nonlocal bytes_transferred
                    bytes_transferred += bytes_read
                    if progress_callback:
                        progress_callback(bytes_transferred, file_size)

                jid = self.upload_chunk(
                    server_url=init_res.server_url,
                    signed_id=signed_id,
                    chunk_data=chunk,
                    on_progress=on_chunk_bytes if progress_callback else None,
                )
                uploaded_parts.append({"number": part_num, "id": jid})

                # Ensure bytes_transferred aligns after chunk finishes
                part_cumulative = min(part_num * part_size, file_size)
                if bytes_transferred < part_cumulative:
                    bytes_transferred = part_cumulative
                    if progress_callback:
                        progress_callback(bytes_transferred, file_size)

        return self.complete_upload(
            signature_id=init_res.signature,
            parts=uploaded_parts,
        )

    def upload_bytes(
        self,
        data: Union[bytes, bytearray],
        filename: str,
        parent_id: str = "",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> FlezenFile:
        """
        High-level helper to upload in-memory bytes using the 3-step chunked engine.

        :param data: Binary content.
        :param filename: Filename for the uploaded object.
        :param parent_id: Optional parent folder ID.
        :param progress_callback: Optional callback fn(uploaded_bytes, total_bytes).
        :return: FlezenFile metadata.
        """
        file_size = len(data)
        init_res = self.initiate_upload(name=filename, size=file_size, parent_id=parent_id)

        part_size = init_res.part_size
        total_parts = max(1, math.ceil(file_size / part_size))
        signed_ids = init_res.signed_ids

        uploaded_parts = []
        bytes_transferred = 0

        for part_num in range(1, total_parts + 1):
            start = (part_num - 1) * part_size
            end = min(start + part_size, file_size)
            chunk = data[start:end]

            signed_id_index = part_num - 1
            if signed_id_index < len(signed_ids):
                signed_id = signed_ids[signed_id_index]
            else:
                signed_id = signed_ids[-1]

            def on_chunk_bytes(bytes_read: int):
                nonlocal bytes_transferred
                bytes_transferred += bytes_read
                if progress_callback:
                    progress_callback(bytes_transferred, file_size)

            jid = self.upload_chunk(
                server_url=init_res.server_url,
                signed_id=signed_id,
                chunk_data=chunk,
                on_progress=on_chunk_bytes if progress_callback else None,
            )
            uploaded_parts.append({"number": part_num, "id": jid})

            part_cumulative = min(part_num * part_size, file_size)
            if bytes_transferred < part_cumulative:
                bytes_transferred = part_cumulative
                if progress_callback:
                    progress_callback(bytes_transferred, file_size)


        return self.complete_upload(
            signature_id=init_res.signature,
            parts=uploaded_parts,
        )

    def upload_from_url(
        self,
        url: str,
        custom_name: Optional[str] = None,
        parent_id: str = "",
        headers: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> FlezenFile:
        """
        Upload a file directly from a public URL.

        Streams the file from the remote URL and uploads it directly to Flezen's
        edge storage nodes using chunked multi-part streaming without high RAM usage.

        :param url: Direct HTTP/HTTPS download link.
        :param custom_name: Optional custom filename to store as.
        :param parent_id: Optional parent folder ID.
        :param headers: Optional HTTP headers for fetching the remote URL.
        :param progress_callback: Optional callback fn(uploaded_bytes, total_bytes).
        :return: FlezenFile metadata.
        """
        fetch_headers = {
            "User-Agent": self.DEFAULT_USER_AGENT,
        }
        if headers:
            fetch_headers.update(headers)

        try:
            res = requests.get(url, headers=fetch_headers, stream=True, timeout=self.timeout)
        except requests.RequestException as e:
            raise FlezenUploadError(f"Failed to fetch remote URL {url}: {e}") from e

        if not res.ok:
            raise FlezenUploadError(
                f"Failed to download remote file (HTTP {res.status_code}): {res.text[:200]}"
            )

        file_name = custom_name or _extract_filename_from_url(url, res)
        content_length_str = res.headers.get("Content-Length")

        if content_length_str and content_length_str.isdigit() and int(content_length_str) > 0:
            file_size = int(content_length_str)
            if file_size < 1024:
                raise FlezenUploadError(
                    f"Flezen requires a minimum file size of 1KB (1,024 bytes). Remote file is {file_size} bytes."
                )

            init_res = self.initiate_upload(name=file_name, size=file_size, parent_id=parent_id)
            part_size = init_res.part_size
            total_parts = max(1, math.ceil(file_size / part_size))
            signed_ids = init_res.signed_ids

            uploaded_parts = []
            bytes_transferred = 0
            stream_iterator = iter(res.iter_content(chunk_size=65536))

            for part_num in range(1, total_parts + 1):
                part_buffer = bytearray()
                while len(part_buffer) < part_size:
                    try:
                        chunk = next(stream_iterator)
                        if not chunk:
                            break
                        part_buffer.extend(chunk)
                    except StopIteration:
                        break

                if not part_buffer and part_num > 1:
                    break

                chunk_bytes = bytes(part_buffer)
                signed_id_index = part_num - 1
                signed_id = signed_ids[signed_id_index] if signed_id_index < len(signed_ids) else signed_ids[-1]

                def on_chunk_bytes(bytes_read: int):
                    nonlocal bytes_transferred
                    bytes_transferred += bytes_read
                    if progress_callback:
                        progress_callback(bytes_transferred, file_size)

                jid = self.upload_chunk(
                    server_url=init_res.server_url,
                    signed_id=signed_id,
                    chunk_data=chunk_bytes,
                    on_progress=on_chunk_bytes if progress_callback else None,
                )
                uploaded_parts.append({"number": part_num, "id": jid})

                part_cumulative = min(part_num * part_size, file_size)
                if bytes_transferred < part_cumulative:
                    bytes_transferred = part_cumulative
                    if progress_callback:
                        progress_callback(bytes_transferred, file_size)

            return self.complete_upload(
                signature_id=init_res.signature,
                parts=uploaded_parts,
            )
        else:
            # Fallback when Content-Length is missing: buffer to a temp file
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                temp_path = tmp.name
                for chunk in res.iter_content(chunk_size=65536):
                    if chunk:
                        tmp.write(chunk)

            try:
                temp_size = os.path.getsize(temp_path)
                if temp_size < 1024:
                    raise FlezenUploadError(
                        f"Flezen requires a minimum file size of 1KB (1,024 bytes). Remote file is {temp_size} bytes."
                    )
                return self.upload_file(
                    file_path=temp_path,
                    parent_id=parent_id,
                    custom_name=file_name,
                    progress_callback=progress_callback,
                )
            finally:
                Path(temp_path).unlink(missing_ok=True)


    # =========================================================================
    # 5. Files & Storage Management
    # =========================================================================

    def list_files(
        self,
        page: int = 1,
        parent_id: Optional[str] = None,
        sort_by: str = "name",
        sort_order: str = "asc",
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List files and folders.

        :param page: Page number (default: 1).
        :param parent_id: Folder ID to list contents for.
        :param sort_by: Sorting field ('name', 'time', 'size', 'views').
        :param sort_order: Sort order ('asc', 'desc').
        :param query: Optional search keyword.
        :return: Dict with 'total', 'request', 'files' (as FlezenFile objects), and raw files.
        """
        params: Dict[str, Any] = {
            "page": page,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
        if parent_id is not None:
            params["parent_id"] = parent_id
        if query:
            params["query"] = query

        res = self._request("GET", "/user/api/files", params=params)
        data = res.json()

        files_list = [FlezenFile.from_dict(f) for f in data.get("files", [])]
        return {
            "total": data.get("total", len(files_list)),
            "request": data.get("request", {}),
            "files": files_list,
            "raw": data,
        }

    def get_storage_usage(self) -> StorageUsage:
        """
        Get storage usage breakdown.
        """
        res = self._request("GET", "/user/api/usage/storage")
        return StorageUsage.from_dict(res.json())

    def create_folder(self, name: str, parent_id: str = "") -> Dict[str, Any]:
        """
        Create a new folder in storage.
        """
        res = self._request(
            "POST",
            "/user/api/files/create-folder",
            json={"name": name, "parent_id": parent_id},
        )
        return res.json()

    def move_file(self, slug: str, parent_id: str = "") -> Dict[str, Any]:
        """
        Move a file or folder into another directory.
        """
        res = self._request(
            "POST",
            "/user/api/files/move",
            json={"slug": slug, "parent_id": parent_id},
        )
        return res.json()

    def modify_file(
        self,
        slug: str,
        name: Optional[str] = None,
        visibility: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update file properties (e.g. rename or toggle public/private visibility).
        """
        payload: Dict[str, Any] = {"slug": slug}
        if name is not None:
            payload["name"] = name
        if visibility is not None:
            if visibility not in ("public", "private"):
                raise ValueError("visibility must be 'public' or 'private'")
            payload["visibility"] = visibility

        res = self._request("POST", "/user/api/files/modify", json=payload)
        return res.json()

    def delete_file(self, slug: str) -> bool:
        """
        Delete a file by its slug. Returns True on success (HTTP 204 or 200).
        """
        res = self._request("DELETE", "/user/api/files/delete", json={"slug": slug})
        return res.status_code in (200, 204)

    def copy_file(self, slug: str) -> Dict[str, Any]:
        """
        Clone / Remote Copy a file.
        """
        res = self._request("POST", "/user/api/files/copy", data={"slug": slug})
        try:
            return res.json()
        except Exception:
            return {"success": True}

    # =========================================================================
    # 6. Analytics & Monetization
    # =========================================================================

    def get_stats(self, period: str = "weekly") -> Dict[str, Any]:
        """
        Get monetization views and earnings stats.

        :param period: 'weekly', 'monthly', or 'daily'.
        """
        valid_periods = ("weekly", "monthly", "daily")
        if period not in valid_periods:
            raise ValueError(f"Period must be one of {valid_periods}")

        res = self._request("GET", f"/user/api/stats/{period}")
        return res.json()

    def get_traffic_sources(self) -> List[Dict[str, Any]]:
        """
        List approved traffic source whitelist URLs.
        """
        res = self._request("GET", "/user/api/traffic-sources")
        return res.json()

    def add_traffic_source(self, link: str) -> Dict[str, Any]:
        """
        Add a traffic source whitelist link (e.g. Telegram channel).
        """
        res = self._request("PUT", "/user/api/traffic-sources", json={"link": link})
        try:
            return res.json()
        except Exception:
            return {"success": True, "link": link}

    def remove_traffic_source(self, link: str) -> Dict[str, Any]:
        """
        Remove a traffic source whitelist link.
        """
        res = self._request("DELETE", "/user/api/traffic-sources", json={"link": link})
        try:
            return res.json()
        except Exception:
            return {"success": True, "link": link}

    # =========================================================================
    # 7. Payouts & Finance
    # =========================================================================

    def get_payment_details(self) -> Dict[str, Any]:
        """
        Get saved payout methods and details.
        """
        res = self._request("GET", "/user/profile/payment/details")
        return res.json()

    def set_payment_upi(self, name: str, upi_id: str) -> Dict[str, Any]:
        """
        Configure UPI payout details ($5.00 min - $60.00 max).
        """
        payload = {
            "method": "upi",
            "details": {"name": name, "upi": upi_id},
        }
        res = self._request("POST", "/user/profile/payment/details", json=payload)
        return res.json()

    def set_payment_paypal(self, name: str, email: str) -> Dict[str, Any]:
        """
        Configure PayPal payout details (balances > $60.00).
        """
        payload = {
            "method": "paypal",
            "details": {"name": name, "email": email},
        }
        res = self._request("POST", "/user/profile/payment/details", json=payload)
        return res.json()

    def set_payment_bank(
        self,
        name: str,
        account: str,
        ifsc: str,
        account_type: Union[int, str] = 1,
    ) -> Dict[str, Any]:
        """
        Configure direct Bank payout details (1: Savings, 2: Current, 3: NRE).
        """
        payload = {
            "method": "bank",
            "details": {
                "name": name,
                "account": str(account),
                "ifsc": ifsc,
                "type": str(account_type),
            },
        }
        res = self._request("POST", "/user/profile/payment/details", json=payload)
        return res.json()

    def request_withdrawal(self, method: str) -> Dict[str, Any]:
        """
        Submit a withdrawal request.

        :param method: 'upi', 'paypal', or 'bank'.
        """
        method_lower = method.lower()
        if method_lower not in ("upi", "paypal", "bank"):
            raise ValueError("Withdrawal method must be 'upi', 'paypal', or 'bank'")

        res = self._request("POST", "/user/withdraw/request", json={"method": method_lower})
        return res.json()

    def get_withdrawal_history(self, page: int = 1) -> Dict[str, Any]:
        """
        Get withdrawal transaction history.
        """
        res = self._request("GET", "/user/api/withdraw/history", params={"page": page})
        return res.json()

    # =========================================================================
    # 8. Notifications & Support Tickets
    # =========================================================================

    def get_unread_notifications_count(self) -> int:
        """
        Get count of unread notifications.
        """
        res = self._request("GET", "/user/api/notifications/unread")
        data = res.json()
        return data.get("count", 0)

    def get_notifications(self) -> List[Dict[str, Any]]:
        """
        Get list of account notifications.
        """
        res = self._request("GET", "/user/api/notifications")
        return res.json()

    def mark_notification_as_read(self, notification_id: int = 0) -> Dict[str, Any]:
        """
        Mark a notification as read (notification_id=0 marks all notifications as read).
        """
        res = self._request("PUT", f"/user/api/notifications/mark-as-read/{notification_id}")
        try:
            return res.json()
        except Exception:
            return {"success": True}

    def list_tickets(self, page: int = 1) -> Dict[str, Any]:
        """
        List user support tickets.
        """
        res = self._request("GET", "/user/api/tickets", params={"page": page})
        return res.json()

    def create_ticket(self, subject: str, body: str) -> Dict[str, Any]:
        """
        Open a new support ticket.
        """
        res = self._request("POST", "/user/tickets", data={"subject": subject, "body": body})
        try:
            return res.json()
        except Exception:
            return {"success": True}

    def get_ticket(self, ticket_id: Union[int, str]) -> Dict[str, Any]:
        """
        Get ticket thread messages and status.
        """
        res = self._request("GET", f"/user/tickets/{ticket_id}")
        try:
            return res.json()
        except Exception:
            return {"success": True, "content": res.text}

    # =========================================================================
    # 9. Account Security & Revocation
    # =========================================================================

    def revoke_session(self, session_id: str) -> Dict[str, Any]:
        """
        Revoke an active session by its ID.
        """
        res = self._request("POST", "/user/api/profile/revoke-session", json={"session_id": session_id})
        return res.json()

    def revoke_all_sessions(self) -> Dict[str, Any]:
        """
        Revoke all other active sessions except the current one.
        """
        res = self._request("POST", "/user/api/profile/revoke-all-sessions")
        try:
            return res.json()
        except Exception:
            return {"success": True}

    def revoke_bot_key(self) -> Dict[str, Any]:
        """
        Revoke the Telegram Bot API key.
        """
        res = self._request("POST", "/user/bots/revoke")
        try:
            return res.json()
        except Exception:
            return {"success": True}

    def change_password(
        self,
        old_password: str,
        new_password: str,
        confirm_password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Change account password.
        """
        payload = {
            "old_password": old_password,
            "new_password": new_password,
            "confirm_password": confirm_password or new_password,
        }
        res = self._request("POST", "/user/profile/change-password", json=payload)
        return res.json()

    def delete_account_request(self, password: str) -> Dict[str, Any]:
        """
        Step 1 of Account Deletion: Triggers OTP email.
        """
        res = self._request("POST", "/user/api/delete-account", json={"password": password})
        return res.json()

    def delete_account_resend_otp(self) -> Dict[str, Any]:
        """
        Step 2 of Account Deletion: Resend OTP email.
        """
        res = self._request("POST", "/user/api/delete-account/resend")
        return res.json()

    def delete_account_confirm(self, otp: str) -> Dict[str, Any]:
        """
        Step 3 of Account Deletion: Confirm deletion with email OTP.
        """
        res = self._request("POST", "/user/api/delete-account/confirm", json={"otp": otp})
        return res.json()
