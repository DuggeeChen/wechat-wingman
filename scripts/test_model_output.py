"""Regression for HTTP 200 with empty/truncated model output. Synthetic data only."""
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

CAPTURE = json.dumps({"name": "虚构联系人", "kind": "单聊", "messages": [
    {"role": "other", "side": "left", "bbox": [0.2, 0.2, 0.6, 0.3], "text": "测试消息 {一}[二]"}]}, ensure_ascii=False)


def completion(content=CAPTURE, finish="stop"):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}]}


class CaptureFormatTests(unittest.TestCase):
    def test_complete_capture_accepts_bom_case_insensitive_fence_and_short_prose(self):
        for text in (CAPTURE, "\ufeff" + CAPTURE, "```JSON\n" + CAPTURE + "\n```",
                     "识别结果如下：\n" + CAPTURE + "\n以上为可见消息。"):
            self.assertEqual(C.parse_capture(text)["messages"][0]["text"], "测试消息 {一}[二]")

    def test_truncation_multiple_objects_array_and_duplicate_identity_stay_invalid(self):
        for text in (CAPTURE[:-2], CAPTURE + CAPTURE, "[" + CAPTURE + "]",
                     '{"role":"self","role":"other"}',
                     '{"broken":' + CAPTURE, "", None):
            with self.assertRaises(ValueError):
                C.unpack_json(text)

    def test_wrapper_does_not_weaken_spatial_identity_check(self):
        text = "识别结果：" + CAPTURE.replace('"other"', '"self"')
        self.assertEqual(C.parse_capture(text)["messages"][0]["role"], "unknown")


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.cfg = copy.deepcopy(core.DEFAULT_CFG)
        self.cfg.update(api_base="https://api.deepseek.com", model="deepseek-flash",
                        fallback_models=[], send_reasoning_effort=False)
        self.log = patch.object(core, "log")
        self.logger = self.log.start()

    def tearDown(self):
        self.log.stop()

    def call(self, **kwargs):
        return core.call_model(self.cfg, "fake-key", "synthetic-image", C.CAPTURE_PROMPT,
                               stage=kwargs.pop("stage", "capture"), **kwargs)

    def test_official_capture_forces_json_and_disables_thinking_without_config_mutation(self):
        original = copy.deepcopy(self.cfg)
        with patch.object(core, "_bounded_post", return_value=((200, completion(), None), None)) as post:
            self.assertEqual(self.call(), (CAPTURE, None))
        payload = post.call_args.args[2]
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertIn("JSON", payload["messages"][0]["content"])
        self.assertEqual(self.cfg, original)

    def test_generation_keeps_thinking_preference_and_legacy_has_no_added_parameters(self):
        with patch.object(core, "_bounded_post", return_value=((200, completion("OK"), None), None)) as post:
            self.assertEqual(self.call(stage="generate"), ("OK", None))
            self.assertNotIn("thinking", post.call_args.args[2])
            self.assertIn("response_format", post.call_args.args[2])
            self.assertEqual(self.call(stage=None), ("OK", None))
            self.assertNotIn("response_format", post.call_args.args[2])

    def test_custom_and_lookalike_endpoints_never_receive_provider_parameters_or_retry(self):
        for base in ("https://another.example/v1", "https://api.deepseek.com.evil.example",
                     "https://api.deepseek.com/proxy", "https://api.deepseek.com:444"):
            self.cfg["api_base"] = base
            with patch.object(core, "_bounded_post", return_value=((200, completion(""), None), None)) as post:
                self.assertIn("正文", self.call()[1])
                self.assertEqual(post.call_count, 1)
                self.assertNotIn("thinking", post.call_args.args[2])
                self.assertNotIn("response_format", post.call_args.args[2])

    def test_recovery_of_empty_length_or_malformed_uses_same_image_prompt_and_deadline(self):
        for first in (completion(""), completion(None), completion(CAPTURE[:-3]), completion(CAPTURE, "length")):
            deadline = time.monotonic()+8
            with patch.object(core, "_bounded_post", side_effect=[((200, first, None), None),
                              ((200, completion(), None), None)]) as post:
                self.assertEqual(self.call(deadline=deadline), (CAPTURE, None))
            self.assertEqual(post.call_count, 2)
            self.assertEqual(post.call_args_list[0].args[2], post.call_args_list[1].args[2])
            self.assertTrue(all(c.args[4] == deadline for c in post.call_args_list))

    def test_only_one_recovery_and_no_raw_chat_or_credential_in_diagnostics(self):
        with patch.object(core, "_bounded_post", return_value=((200, completion(""), None), None)) as post:
            text, error = self.call()
        self.assertEqual(text, "")
        self.assertIn("正文", error)
        self.assertEqual(post.call_count, 2)
        logs = "\n".join(args[0] for args, _ in self.logger.call_args_list)
        self.assertIn("output_error=empty", logs)
        self.assertNotIn("fake-key", logs)
        self.assertNotIn("虚构联系人", logs)

    def test_http_auth_filter_and_cancel_do_not_trigger_recovery(self):
        for response in (((401, None, None), None), ((200, completion("", "content_filter"), None), None),
                         (None, "cancel")):
            with patch.object(core, "_bounded_post", return_value=response) as post:
                self.assertIsNotNone(self.call()[1])
                self.assertEqual(post.call_count, 1)

    def test_cancellation_after_empty_response_prevents_second_request(self):
        cancelled = threading.Event()
        def first(*args, **kwargs):
            cancelled.set()
            return (200, completion(""), None), None
        with patch.object(core, "_bounded_post", side_effect=first) as post:
            self.assertEqual(self.call(cancel_event=cancelled), ("", "已取消"))
            self.assertEqual(post.call_count, 1)

    def test_not_enough_remaining_budget_skips_recovery(self):
        clock = [0]
        def first(*args, **kwargs):
            clock[0] = 3
            return (200, completion(""), None), None
        with patch.object(core.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(core, "_bounded_post", side_effect=first) as post:
            self.assertIn("正文", self.call(deadline=4)[1])
            self.assertEqual(post.call_count, 1)


class OutputHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.send_header("Content-Type", self.server.content_type)
        self.send_header("Content-Length", str(len(self.server.body)))
        self.end_headers()
        self.wfile.write(self.server.body)

    def log_message(self, *args):
        pass


class TransportOutputTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), OutputHandler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cfg = copy.deepcopy(core.DEFAULT_CFG)
        self.cfg.update(api_base="http://127.0.0.1:%d" % self.server.server_port,
                        fallback_models=[], send_reasoning_effort=False)
        self.log = patch.object(core, "log")
        self.log.start()

    def tearDown(self):
        end = time.monotonic()+1
        while time.monotonic() < end:
            if core._http_slots.acquire(blocking=False):
                second = core._http_slots.acquire(blocking=False)
                if second:
                    core._http_slots.release()
                core._http_slots.release()
                if second:
                    break
            time.sleep(0.005)
        while True:
            try:
                _, session = core._http_sessions.get_nowait()
                session.close()
            except queue.Empty:
                break
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(1)
        self.log.stop()

    def call(self, content, finish="stop", sse=True):
        self.server.content_type = "text/event-stream" if sse else "application/json"
        if sse:
            # Thinking is deliberately never added to content or progress.
            chunks = [{"choices": [{"delta": {"reasoning_content": "private synthetic thinking"}}]},
                      {"choices": [{"delta": {"content": content}, "finish_reason": finish}]}]
            self.server.body = ("".join("data: " + json.dumps(c) + "\n\n" for c in chunks)
                                + "data: [DONE]\n\n").encode()
        else:
            self.server.body = json.dumps(completion(content, finish)).encode()
        return core.call_model(self.cfg, "fake-key", None, C.CAPTURE_PROMPT, stage="capture")

    def test_sse_length_is_not_lost_even_if_content_is_complete_json(self):
        self.assertIn("截断", self.call(CAPTURE, "length")[1])

    def test_sse_thinking_only_and_whitespace_are_not_success(self):
        for content in (None, "", "   "):
            self.assertIn("正文", self.call(content)[1])

    def test_json_empty_and_length_are_not_success(self):
        self.assertIn("正文", self.call(None, sse=False)[1])
        self.assertIn("截断", self.call(CAPTURE, "length", sse=False)[1])

    def test_sse_filter_or_server_abort_cannot_be_parsed_as_success(self):
        for reason in ("content_filter", "aborted", "insufficient_system_resource", "tool_calls"):
            self.assertIn("未完成", self.call(CAPTURE, reason)[1])

    def test_done_and_nonstream_compatibility_without_finish_reason(self):
        self.assertEqual(self.call(CAPTURE, None), (CAPTURE, None))
        self.assertEqual(self.call(CAPTURE, None, sse=False), (CAPTURE, None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
