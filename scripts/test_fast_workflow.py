"""Synthetic workflow tests and real loopback HTTP connection reuse tests."""
import copy
import json
import os
import queue
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import buddy_context as C
import wx_helper as core
from buddy_ui import BuddyApp


def captured(name="林", role="other", text="这周能帮忙吗？"):
    side = "right" if role == "self" else "left"
    box = [0.7, 0.2, 0.95, 0.3] if role == "self" else [0.2, 0.2, 0.6, 0.3]
    return json.dumps({"name": name, "kind": "单聊", "messages": [
        {"text": text, "role": role, "side": side, "bbox": box}]}, ensure_ascii=False)


REPLY = json.dumps({"candidates": [{"label": "问清范围", "text": "具体需要做什么？"}], "facts": []}, ensure_ascii=False)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.app = BuddyApp(core, copy.deepcopy(core.DEFAULT_CFG), "dummy", testing=True)
        self.frame = core.Image.new("RGB", (680, 480), "white")
        self.patches = [patch.object(core, "log"), patch.object(core, "find_wechat", return_value=("ok", 123)),
                        patch.object(core, "capture_wechat", side_effect=lambda _hwnd, **_: self.frame.copy())]
        for p in self.patches:
            p.start()

    def tearDown(self):
        self.app.close()
        for p in reversed(self.patches):
            p.stop()

    def run_mode(self, mode):
        self.app.start(mode)
        end = time.monotonic()+3
        while self.app.busy and time.monotonic() < end:
            try:
                self.app.handle_event(*self.app.q.get_nowait())
            except queue.Empty:
                time.sleep(0.005)
            self.app.root.update()
        self.assertFalse(self.app.busy, "workflow did not finish")

    def first_read(self, role="other"):
        with patch.object(core, "call_model", return_value=(captured(role=role), None)):
            self.run_mode("read")

    def test_one_click_chains_image_then_text_and_repeated_click_reuses_reply(self):
        with patch.object(core, "call_model", side_effect=[(captured(), None), (REPLY, None)]) as call:
            self.run_mode("read_generate")
            self.assertEqual(call.call_count, 2)
            self.assertTrue(call.call_args_list[0].args[2])
            self.assertIsNone(call.call_args_list[1].args[2])
            self.assertEqual(self.app.cards[0]["text"], "具体需要做什么？")
        with patch.object(core, "call_model") as call:
            self.run_mode("read_generate")
            call.assert_not_called()
            self.assertEqual(self.app.cards[0]["text"], "具体需要做什么？")

    def test_cached_read_preserves_manual_correction_target_and_existing_reply(self):
        self.first_read()
        a = self.app
        mid = a.active.messages[0]["id"]
        a.active.edit(mid, "self", "我纠正的正文")
        a.select_target(mid)
        a.cards = [{"label": "补充", "text": "已确认的回复"}]
        with patch.object(core, "call_model") as call:
            self.run_mode("read")
            call.assert_not_called()
        self.assertEqual(a.active.messages[0]["text"], "我纠正的正文")
        self.assertEqual(a.active.messages[0]["role"], "self")
        self.assertEqual(a.active.target_id, mid)
        self.assertTrue(a.active.explicit_target)
        self.assertEqual(a.cards[0]["text"], "已确认的回复")

    def test_changed_style_or_requirements_reuse_image_but_generate_new_reply(self):
        with patch.object(core, "call_model", side_effect=[(captured(), None), (REPLY, None)]):
            self.run_mode("read_generate")
        a = self.app
        a.cfg["personas"][a.persona.get()] = "新的说话风格"
        with patch.object(core, "call_model", return_value=(REPLY, None)) as call:
            self.run_mode("read_generate")
            self.assertEqual(call.call_count, 1)
            self.assertIsNone(call.call_args.args[2])
            self.assertIn("新的说话风格", call.call_args.args[3])
        a.boundary.set("不承诺交付时间")
        a.plan_changed()
        with patch.object(core, "call_model", return_value=(REPLY, None)) as call:
            self.run_mode("read_generate")
            self.assertEqual(call.call_count, 1)
            self.assertIsNone(call.call_args.args[2])
            self.assertIn("不承诺交付时间", call.call_args.args[3])

    def test_cache_can_use_corrected_unknown_identity_for_text_generation(self):
        self.first_read(role="unknown")
        a = self.app
        a.active.edit(a.active.messages[0]["id"], "other", "请先问我具体范围")
        a.invalidate()
        with patch.object(core, "call_model", return_value=(REPLY, None)) as call:
            self.run_mode("read_generate")
            self.assertEqual(call.call_count, 1)
            self.assertIsNone(call.call_args.args[2])
            self.assertIn("请先问我具体范围", call.call_args.args[3])

    def test_single_pixel_change_requires_recognition(self):
        self.first_read()
        self.frame.putpixel((4, 4), (0, 0, 0))
        with patch.object(core, "call_model", return_value=(captured(), None)) as call:
            self.run_mode("read")
            self.assertEqual(call.call_count, 1)
            self.assertTrue(call.call_args.args[2])

    def test_model_change_window_change_and_older_mode_cannot_hit_cache(self):
        self.first_read()
        a = self.app
        a.cfg["model"] = "another-model"
        with patch.object(core, "call_model", return_value=(captured(), None)) as call:
            self.run_mode("read")
            self.assertEqual(call.call_count, 1)
        with patch.object(core, "find_wechat", return_value=("ok", 456)), \
             patch.object(core, "call_model", return_value=(captured(), None)) as call:
            self.run_mode("read")
            self.assertEqual(call.call_count, 1)
            self.run_mode("older")
            self.assertEqual(call.call_count, 2)

    def test_switch_session_and_clear_cannot_use_previous_cache(self):
        self.first_read()
        a = self.app
        first = a.active
        a.activate(C.Conversation("林"))
        self.assertIsNone(a.capture_cache)
        a.activate(first)
        with patch.object(core, "call_model", return_value=(captured(), None)) as call:
            self.run_mode("read")
            self.assertEqual(call.call_count, 1)
        with patch("buddy_ui.messagebox.askyesno", return_value=True):
            a.clear_session()
        with patch.object(core, "call_model", return_value=(captured(), None)) as call:
            self.run_mode("read")
            self.assertEqual(call.call_count, 1)

    def test_unknown_identity_and_self_last_stop_before_generation(self):
        for role in ("unknown", "self"):
            self.app.activate(C.Conversation("林"))
            with patch.object(core, "call_model", return_value=(captured(role=role), None)) as call:
                self.run_mode("read_generate")
                self.assertEqual(call.call_count, 1)
                self.assertEqual(self.app.cards, [])

    def test_other_contact_and_missing_overlap_stop_before_generation(self):
        self.first_read()
        a = self.app
        with patch.object(a, "resolve_pending"), \
             patch.object(core, "call_model", return_value=(captured(name="赵"), None)) as call:
            self.frame.putpixel((0, 0), (0, 0, 0))
            self.run_mode("read_generate")
            self.assertEqual(call.call_count, 1)
            self.assertEqual(a.active.name, "林")
            self.assertIsNotNone(a.pending_capture)
        a.pending_capture = None
        with patch.object(a, "resolve_pending"), \
             patch.object(core, "call_model", return_value=(captured(text="另一个不重叠片段"), None)) as call:
            self.run_mode("read_generate")
            self.assertEqual(call.call_count, 1)
            self.assertIsNotNone(a.active.pending)

    def test_failed_generation_retry_is_text_only(self):
        with patch.object(core, "call_model", side_effect=[(captured(), None), ("", "响应超时")]) as call:
            self.run_mode("read_generate")
            self.assertEqual(call.call_count, 2)
        self.assertEqual(self.app.last_retry[0], "generate")
        self.assertTrue(self.app.active.messages)
        with patch.object(core, "call_model", return_value=(REPLY, None)) as call:
            self.run_mode(self.app.last_retry[0])
            self.assertEqual(call.call_count, 1)
            self.assertIsNone(call.call_args.args[2])

    def test_cancelled_capture_and_late_cache_event_cannot_continue(self):
        a = self.app
        with patch.object(core, "call_model") as call:
            a.network_mode = "read_generate"
            job = a.epoch
            a.cancel()
            a.handle_event(job, "capture", (C.parse_capture(captured()), False))
            a.handle_event(job, "reused", "old-session")
            call.assert_not_called()
            self.assertIsNone(a.active)
            self.assertIsNone(a.capture_cache)

    def test_all_footer_controls_fit_minimum_size(self):
        a = self.app
        a.root.deiconify()
        a.root.geometry("500x620")
        a.root.update()
        for b in (a.quick_button, a.go_button, a.more_button):
            self.assertTrue(b.winfo_ismapped())
            self.assertLessEqual(b.winfo_rooty()-a.root.winfo_rooty()+b.winfo_height(), a.root.winfo_height())


class LoopbackServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args):
        self.accepts = 0
        self.received = []
        super().__init__(*args)

    def get_request(self):
        result = super().get_request()
        self.accepts += 1
        return result


class ModelHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.received.append(dict(self.headers))
        if data.get("stream"):
            body = (b'data: {"choices":[{"delta":{"content":"OK"},"finish_reason":"stop"}]}\n\n'
                    b'data: [DONE]\n\n')
            content_type = "text/event-stream"
        else:
            body = b'{"choices":[{"message":{"content":"OK"}}]}'
            content_type = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        chunked = data.get("stream")
        self.send_header("Transfer-Encoding" if chunked else "Content-Length", "chunked" if chunked else str(len(body)))
        self.send_header("Set-Cookie", "test_session=private; Path=/")
        self.end_headers()
        if chunked:
            self.wfile.write(("%X\r\n" % len(body)).encode()+body+b"\r\n")
            self.wfile.flush()
            # DONE has arrived; HTTP has not finished. A real streaming endpoint.
            if getattr(self.server, "tail_release", None) is not None:
                self.server.tail_release.wait(2)
            self.wfile.write(b"0\r\n\r\n")
        else:
            self.wfile.write(body)
        self.wfile.flush()

    def log_message(self, *args):
        pass


class ConnectionTests(unittest.TestCase):
    def drain(self):
        while True:
            try:
                _origin, session = core._http_sessions.get_nowait()
                session.close()
            except queue.Empty:
                return

    def setUp(self):
        self.drain()
        self.server = LoopbackServer(("127.0.0.1", 0), ModelHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cfg = copy.deepcopy(core.DEFAULT_CFG)
        self.cfg.update(api_base="http://127.0.0.1:%d/v1" % self.server.server_port, fallback_models=[], stream_responses=False)
        self.log = patch.object(core, "log")
        self.log.start()

    def tearDown(self):
        self.drain()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(1)
        self.log.stop()

    def call(self, key="fake-key"):
        self.assertEqual(core.call_model(self.cfg, key, None, "synthetic prompt"), ("OK", None))
        # Cleanup runs after the worker publishes its result.
        end = time.monotonic()+1
        while core._http_sessions.empty() and time.monotonic() < end:
            time.sleep(0.005)

    def test_json_and_sse_use_one_connection_and_current_auth_without_cookies(self):
        self.call("fake-first")
        self.cfg["stream_responses"] = True
        self.call("fake-second")
        self.call("fake-third")
        self.assertEqual(self.server.accepts, 1)
        self.assertEqual([h["Authorization"] for h in self.server.received],
                         ["Bearer fake-first", "Bearer fake-second", "Bearer fake-third"])
        self.assertTrue(all("Cookie" not in h for h in self.server.received))
        _, session = core._http_sessions.queue[-1]
        self.assertNotIn("Authorization", session.headers)
        self.assertEqual(len(session.cookies), 0)

    def test_changing_endpoint_drops_previous_idle_session(self):
        self.call()
        _, previous = core._http_sessions.queue[-1]
        second = LoopbackServer(("127.0.0.1", 0), ModelHandler)
        thread = threading.Thread(target=second.serve_forever, daemon=True)
        thread.start()
        try:
            self.cfg["api_base"] = "http://127.0.0.1:%d/v1" % second.server_port
            with patch.object(previous, "close", wraps=previous.close) as close:
                self.call("fake-new-provider")
                close.assert_called_once()
            self.assertEqual(second.accepts, 1)
            self.assertEqual(second.received[0]["Authorization"], "Bearer fake-new-provider")
        finally:
            self.drain()
            second.shutdown()
            second.server_close()
            thread.join(1)

    def test_reply_does_not_wait_for_http_tail_and_cancelled_tail_is_discarded(self):
        self.cfg["stream_responses"] = True
        self.server.tail_release = threading.Event()
        cancel = threading.Event()
        start = time.monotonic()
        try:
            self.assertEqual(core.call_model(self.cfg, "fake-key", None, "synthetic", cancel_event=cancel), ("OK", None))
            self.assertLess(time.monotonic()-start, 0.5)
            self.assertTrue(core._http_sessions.empty())
            cancel.set()
        finally:
            self.server.tail_release.set()
        # No success/error is published twice; the abandoned session is closed.
        end = time.monotonic()+1
        second = False
        while time.monotonic() < end:
            if core._http_slots.acquire(blocking=False):
                second = core._http_slots.acquire(blocking=False)
                if second:
                    core._http_slots.release()
                core._http_slots.release()
                if second:
                    break
            time.sleep(0.005)
        self.assertTrue(second)
        self.assertTrue(core._http_sessions.empty())


if __name__ == "__main__":
    unittest.main(verbosity=2)
