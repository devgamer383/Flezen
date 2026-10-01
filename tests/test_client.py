"""
Unit tests for the Flezen Python SDK.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from flezen import Flezen, FlezenAPIError, FlezenAuthError, FlezenUploadError
from flezen.models import FlezenFile, StorageUsage


class TestFlezenClient(unittest.TestCase):

    def setUp(self):
        self.mock_session = MagicMock()
        # Mock cookies dict
        self.cookies_dict = {}
        self.mock_session.cookies.get.side_effect = lambda k, default=None: self.cookies_dict.get(k, default)
        self.mock_session.cookies.__contains__.side_effect = lambda k: k in self.cookies_dict
        self.mock_session.cookies.set.side_effect = lambda k, v, **kw: self.cookies_dict.update({k: v})
        self.mock_session.cookies.clear.side_effect = self.cookies_dict.clear

    def test_init_with_tokens(self):
        client = Flezen(fz="jwt_fz_test", rt="uuid_rt_test", session=self.mock_session, auto_login=False)
        self.assertEqual(self.cookies_dict.get("fz"), "jwt_fz_test")
        self.assertEqual(self.cookies_dict.get("rt"), "uuid_rt_test")
        self.assertTrue(client.is_authenticated)
        self.assertEqual(client.fz_token, "jwt_fz_test")
        self.assertEqual(client.rt_token, "uuid_rt_test")

    def test_url_helpers(self):
        slug = "datnfupbjlnn77sojlo0g-myqmbnsvw"
        pub_url = Flezen.get_public_url(slug)
        intent_url = Flezen.get_intent_url(slug)
        app_url = Flezen.get_app_url(slug)

        self.assertEqual(pub_url, f"https://flezen.com/s/{slug}")
        self.assertIn("package=com.devlooper.flezen", intent_url)
        self.assertIn(slug, intent_url)
        self.assertEqual(app_url, f"flezen://flezen.com/s/{slug}")

    def test_login_success(self):
        client = Flezen(email="user@example.com", password="Password123", session=self.mock_session, auto_login=False)
        
        mock_response = MagicMock()
        mock_response.status_code = 302
        mock_response.headers = {"Location": "/user/dashboard"}
        self.mock_session.post.return_value = mock_response

        # Emulate cookies set on redirect
        self.cookies_dict["fz"] = "dummy_fz_jwt"
        
        success = client.login()
        self.assertTrue(success)
        self.mock_session.post.assert_called_once()
        args, kwargs = self.mock_session.post.call_args
        self.assertEqual(args[0], "https://flezen.com/auth/login")
        self.assertEqual(kwargs["data"], {"email": "user@example.com", "password": "Password123"})

    def test_login_failure(self):
        client = Flezen(email="user@example.com", password="WrongPassword", session=self.mock_session, auto_login=False)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<div id="password-error">Invalid email or password</div>'
        mock_response.headers = {}
        self.mock_session.post.return_value = mock_response

        with self.assertRaises(FlezenAuthError) as ctx:
            client.login()
        self.assertIn("Invalid email or password", str(ctx.exception))

    def test_upload_bytes(self):
        client = Flezen(fz="fake_fz", session=self.mock_session, auto_login=False)

        # Mock initiate
        mock_init_resp = MagicMock()
        mock_init_resp.ok = True
        mock_init_resp.status_code = 200
        mock_init_resp.json.return_value = {
            "signature": "sig-12345",
            "signedIDs": ["part_token_1", "part_token_2"],
            "partSize": 10,
            "serverUrl": "https://storage-node.flezen.com",
        }

        # Mock chunk PUT
        mock_chunk_resp = MagicMock()
        mock_chunk_resp.ok = True
        mock_chunk_resp.status_code = 200
        mock_chunk_resp.json.side_effect = [
            {"jId": "jid_chunk_1"},
            {"jId": "jid_chunk_2"},
        ]

        # Mock complete
        mock_complete_resp = MagicMock()
        mock_complete_resp.ok = True
        mock_complete_resp.status_code = 200
        mock_complete_resp.json.return_value = {
            "success": True,
            "file": {
                "name": "test.txt",
                "size": 15,
                "slug": "testslug123",
                "visibility": "public",
            },
        }

        # Mock session.request
        def side_effect_request(method, url, **kwargs):
            if "initiate" in url:
                return mock_init_resp
            elif "complete" in url:
                return mock_complete_resp
            return MagicMock(ok=True, status_code=200, json=lambda: {})

        self.mock_session.request.side_effect = side_effect_request
        self.mock_session.put.return_value = mock_chunk_resp

        data = b"0123456789abcde"  # 15 bytes -> 2 parts (10 + 5)
        progress_calls = []

        def on_progress(uploaded, total):
            progress_calls.append((uploaded, total))

        uploaded_file = client.upload_bytes(data, "test.txt", progress_callback=on_progress)

        self.assertIsInstance(uploaded_file, FlezenFile)
        self.assertEqual(uploaded_file.slug, "testslug123")
        self.assertEqual(uploaded_file.name, "test.txt")
        self.assertEqual(uploaded_file.size, 15)
        self.assertEqual(uploaded_file.public_url, "https://flezen.com/s/testslug123")
        self.assertEqual(self.mock_session.put.call_count, 2)
        self.assertEqual(len(progress_calls), 2)
        self.assertEqual(progress_calls[-1], (15, 15))

    def test_upload_file(self):
        client = Flezen(fz="fake_fz", session=self.mock_session, auto_login=False)

        mock_init_resp = MagicMock(
            ok=True,
            status_code=200,
            json=lambda: {
                "signature": "sig-file-123",
                "signedIDs": ["part_token_1"],
                "partSize": 1024,
                "serverUrl": "https://storage-node.flezen.com",
            }
        )
        mock_chunk_resp = MagicMock(
            ok=True,
            status_code=200,
            json=lambda: {"jId": "jid_1"}
        )
        mock_complete_resp = MagicMock(
            ok=True,
            status_code=200,
            json=lambda: {
                "success": True,
                "file": {
                    "name": "sample.dat",
                    "size": 50,
                    "slug": "sample-slug",
                }
            }
        )

        def side_effect_request(method, url, **kwargs):
            if "initiate" in url:
                return mock_init_resp
            elif "complete" in url:
                return mock_complete_resp
            return MagicMock(ok=True, status_code=200, json=lambda: {})

        self.mock_session.request.side_effect = side_effect_request
        self.mock_session.put.return_value = mock_chunk_resp

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"X" * 50)
            tmp_path = tmp.name

        try:
            uploaded = client.upload_file(tmp_path, custom_name="sample.dat")
            self.assertEqual(uploaded.slug, "sample-slug")
            self.assertEqual(uploaded.name, "sample.dat")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_list_files(self):
        client = Flezen(fz="fake_fz", session=self.mock_session, auto_login=False)

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "total": 1,
            "request": {"page": 1},
            "files": [
                {
                    "name": "photo.png",
                    "size": 1351345,
                    "slug": "datneb9bjlnn769seesgtfq-gnzcfd4",
                    "visibility": "public",
                    "views": 42,
                    "earnings": 0.126,
                }
            ],
        }
        self.mock_session.request.return_value = mock_resp

        res = client.list_files(page=1)
        self.assertEqual(res["total"], 1)
        self.assertEqual(len(res["files"]), 1)
        self.assertIsInstance(res["files"][0], FlezenFile)
        self.assertEqual(res["files"][0].name, "photo.png")
        self.assertEqual(res["files"][0].views, 42)
        self.assertEqual(res["files"][0].earnings, 0.126)

    def test_storage_usage(self):
        client = Flezen(fz="fake_fz", session=self.mock_session, auto_login=False)

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "total_storage_used": 2702690,
            "total_video_storage": 0,
            "total_audio_storage": 0,
            "total_image_storage": 2702690,
            "total_doc_storage": 0,
            "total_other_storage": 0,
        }
        self.mock_session.request.return_value = mock_resp

        usage = client.get_storage_usage()
        self.assertIsInstance(usage, StorageUsage)
        self.assertEqual(usage.total_storage_used, 2702690)
        self.assertEqual(usage.total_image_storage, 2702690)

    def test_folder_and_file_actions(self):
        client = Flezen(fz="fake_fz", session=self.mock_session, auto_login=False)

        # Create folder
        self.mock_session.request.return_value = MagicMock(ok=True, status_code=200, json=lambda: {"id": "fld1"})
        res_folder = client.create_folder("Documents")
        self.assertEqual(res_folder["id"], "fld1")

        # Move file
        self.mock_session.request.return_value = MagicMock(ok=True, status_code=200, json=lambda: {"success": True})
        res_move = client.move_file("slug123", "fld1")
        self.assertTrue(res_move["success"])

        # Modify file
        res_mod = client.modify_file("slug123", name="new_name.png", visibility="private")
        self.assertTrue(res_mod["success"])

        # Delete file
        self.mock_session.request.return_value = MagicMock(ok=True, status_code=204)
        deleted = client.delete_file("slug123")
        self.assertTrue(deleted)

    def test_stats_and_traffic(self):
        client = Flezen(fz="fake_fz", session=self.mock_session, auto_login=False)

        mock_resp = MagicMock(
            ok=True,
            status_code=200,
            json=lambda: {
                "type": "weekly",
                "total_earnings": [0, 0, 0, 0, 0, 0, 0],
                "total_views": [0, 0, 0, 0, 0, 0, 0],
            },
        )
        self.mock_session.request.return_value = mock_resp
        stats = client.get_stats("weekly")
        self.assertEqual(stats["type"], "weekly")

        # Invalid period raises ValueError
        with self.assertRaises(ValueError):
            client.get_stats("invalid_period")

        # Traffic sources
        self.mock_session.request.return_value = MagicMock(
            ok=True,
            status_code=200,
            json=lambda: ["https://t.me/mychannel"],
        )
        sources = client.get_traffic_sources()
        self.assertEqual(sources, ["https://t.me/mychannel"])

    def test_payout_settings(self):
        client = Flezen(fz="fake_fz", session=self.mock_session, auto_login=False)

        self.mock_session.request.return_value = MagicMock(
            ok=True,
            status_code=200,
            json=lambda: {"success": True},
        )
        upi_res = client.set_payment_upi("John Doe", "john@okaxis")
        self.assertTrue(upi_res["success"])

        paypal_res = client.set_payment_paypal("John Doe", "john@example.com")
        self.assertTrue(paypal_res["success"])

        bank_res = client.set_payment_bank("John Doe", "123456789", "SBIN0001", account_type=1)
        self.assertTrue(bank_res["success"])

        withdraw_res = client.request_withdrawal("upi")
        self.assertTrue(withdraw_res["success"])

        # History
        self.mock_session.request.return_value = MagicMock(ok=True, status_code=200, json=lambda: {"history": []})
        hist = client.get_withdrawal_history(page=1)
        self.assertEqual(hist["history"], [])

    def test_notifications_and_tickets(self):
        client = Flezen(fz="fake_fz", session=self.mock_session, auto_login=False)

        # Unread count
        self.mock_session.request.return_value = MagicMock(ok=True, status_code=200, json=lambda: {"count": 3})
        self.assertEqual(client.get_unread_notifications_count(), 3)

        # Notification list
        self.mock_session.request.return_value = MagicMock(ok=True, status_code=200, json=lambda: [{"id": 1, "title": "Welcome"}])
        notifs = client.get_notifications()
        self.assertEqual(len(notifs), 1)

        # Mark read
        self.mock_session.request.return_value = MagicMock(ok=True, status_code=200, json=lambda: {"success": True})
        self.assertTrue(client.mark_notification_as_read(0)["success"])

        # Tickets
        self.mock_session.request.return_value = MagicMock(ok=True, status_code=200, json=lambda: [{"id": 101, "subject": "Issue"}])
        tickets = client.list_tickets(page=1)
        self.assertEqual(len(tickets), 1)

        self.mock_session.request.return_value = MagicMock(ok=True, status_code=200, json=lambda: {"success": True})
        self.assertTrue(client.create_ticket("Help", "Description")["success"])

        self.mock_session.request.return_value = MagicMock(ok=True, status_code=200, json=lambda: {"thread": []})
        thread = client.get_ticket(101)
        self.assertEqual(thread["thread"], [])

    def test_security_and_account_deletion(self):
        client = Flezen(fz="fake_fz", session=self.mock_session, auto_login=False)

        self.mock_session.request.return_value = MagicMock(ok=True, status_code=200, json=lambda: {"success": True})
        self.assertTrue(client.revoke_session("sess_123")["success"])
        self.assertTrue(client.revoke_all_sessions()["success"])
        self.assertTrue(client.revoke_bot_key()["success"])
        self.assertTrue(client.change_password("old", "new", "new")["success"])

        # 3-step account deletion
        self.assertTrue(client.delete_account_request("password123")["success"])
        self.assertTrue(client.delete_account_resend_otp()["success"])
        self.assertTrue(client.delete_account_confirm("123456")["success"])

    def test_register_and_logout(self):
        client = Flezen(session=self.mock_session, auto_login=False)

        # Register success
        mock_reg_resp = MagicMock()
        mock_reg_resp.status_code = 302
        self.mock_session.post.return_value = mock_reg_resp
        self.assertTrue(client.register("newuser@example.com", "Secret123"))

        # Logout
        self.mock_session.request.return_value = MagicMock(ok=True, status_code=200)
        self.cookies_dict["fz"] = "jwt_token"
        self.assertTrue(client.logout())
        self.assertNotIn("fz", self.cookies_dict)

    @patch("flezen.client.requests.get")
    def test_upload_from_url(self, mock_get):
        client = Flezen(fz="fake_fz", session=self.mock_session, auto_login=False)

        # Mock remote URL GET response
        mock_remote_resp = MagicMock()
        mock_remote_resp.ok = True
        mock_remote_resp.status_code = 200
        mock_remote_resp.headers = {
            "Content-Length": "2048",
            "Content-Disposition": 'attachment; filename="remote_file.pdf"',
        }
        mock_remote_resp.iter_content.return_value = [b"A" * 1024, b"B" * 1024]
        mock_get.return_value = mock_remote_resp

        # Mock upload initiate & complete
        client.initiate_upload = MagicMock()
        client.initiate_upload.return_value = MagicMock(
            signature="sig-url",
            signed_ids=["token_1"],
            part_size=1048576,
            server_url="https://storage-node.flezen.com",
        )
        client.upload_chunk = MagicMock(return_value="jid_1")
        client.complete_upload = MagicMock()
        client.complete_upload.return_value = FlezenFile(
            name="remote_file.pdf",
            size=2048,
            slug="urlslug123",
        )

        res = client.upload_from_url("https://example.com/file?id=99")
        self.assertEqual(res.slug, "urlslug123")
        self.assertEqual(res.name, "remote_file.pdf")
        client.initiate_upload.assert_called_once_with(name="remote_file.pdf", size=2048, parent_id="")

    def test_parallel_upload_workers(self):
        client = Flezen(fz="fake_fz", session=self.mock_session, auto_login=False)

        client.initiate_upload = MagicMock(return_value=MagicMock(
            signature="sig-multi",
            signed_ids=["t1", "t2", "t3", "t4"],
            part_size=10,
            server_url="https://storage-node.flezen.com",
        ))
        client.upload_chunk = MagicMock(side_effect=lambda **kw: "jid_" + kw["signed_id"])
        client.complete_upload = MagicMock(side_effect=lambda signature_id, parts: FlezenFile(
            name="multi.bin",
            size=40,
            slug="multislug",
        ))

        data = b"0123456789" * 4  # 40 bytes = 4 parts of 10 bytes
        res = client.upload_bytes(data, filename="multi.bin", workers=4)
        self.assertEqual(res.slug, "multislug")
        self.assertEqual(client.upload_chunk.call_count, 4)
        # Check parts were submitted sorted 1, 2, 3, 4
        parts_arg = client.complete_upload.call_args[1]["parts"]
        self.assertEqual([p["number"] for p in parts_arg], [1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()



