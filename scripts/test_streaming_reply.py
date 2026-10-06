"""Offline streaming contracts and real loopback HTTP -> Tk first-usable reply."""
import copy
import gc
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

FIRST = {"label": "问清范围", "text": '你说的“海报”是几张？\\我先看看。'}
SECOND = {"label": "暂缓表态", "text": "先发我具体内容吧。"}
PREFIX = '{"question":"需要确认数量吗？","candidates":[' + json.dumps(FIRST, ensure_ascii=False)
TAIL = ',' + json.dumps(SECOND, ensure_ascii=False) + '],"situation":"先确认范围。","facts":[]}'
FULL = PREFIX + TAIL


def conversation():
    c = C.Conversation("小林（虚构）")
    c.ingest(C.pasted_messages("对方：明天下午要用，你能帮忙吗？"))
    return c


class ParserTests(unittest.TestCase):
    def test_every_character_boundary_including_escapes_matches_final(self):
        c = conversation()
        collector = C.GenerationStream(c)
        updates = []
        for character in FULL:
            updates.extend(collector.feed(character))
        self.assertFalse(collector.disabled)
        self.assertEqual([len(r["cards"]) for r in updates], [1, 2])
        self.assertEqual(updates[0]["cards"], [FIRST])
        self.assertEqual(updates[-1]["cards"], C.parse_generation(FULL, c)["cards"])
        self.assertEqual(updates[0]["question"], "需要确认数量吗？")

    def test_incomplete_candidate_never_published(self):
        collector = C.GenerationStream(conversation())
        self.assertEqual(collector.feed(PREFIX[:-1]), [])
        self.assertEqual(collector.feed("}" )[0]["cards"], [FIRST])

    def test_reordered_question_waits_until_received(self):
        collector = C.GenerationStream(conversation())
        self.assertEqual(collector.feed('{"candidates":[' + json.dumps(FIRST) + '],'), [])
        self.assertEqual(collector.feed('"question":"先问数量"')[0]["question"], "先问数量")

    def test_fenced_json_and_braces_inside_text(self):
        text = FULL.replace("先发我具体内容吧。", '先发我{数量}和[内容]吧。')
        collector = C.GenerationStream(conversation())
        updates = []
        for ch in "```json\n" + text + "\n```":
            updates.extend(collector.feed(ch))
        self.assertEqual(updates[-1]["cards"], C.parse_generation(text, conversation())["cards"])

    def test_duplicate_fields_and_non_string_replies_rejected(self):
        bad = '{"question":"","candidates":[' + json.dumps(FIRST) + '],"candidates":[]}'
        with self.assertRaises(ValueError):
            C.parse_generation(bad, conversation())
        collector = C.GenerationStream(conversation())
        collector.feed(bad)
        self.assertTrue(collector.disabled)
        with self.assertRaises(ValueError):
            C.parse_generation('{"candidates":[{"text":{"unsafe":"object"}}]}', conversation())

    def test_oversized_prefix_and_unrelated_json_never_preview(self):
        for text in ('{"question":"' + "x"*100001, '{"summary":"检查结果"}'):
            collector = C.GenerationStream(conversation())
            self.assertEqual(collector.feed(text), [])

    def test_long_candidate_is_rejected_instead_of_presenting_half_a_sentence(self):
        data = {"question": "", "candidates": [{"label": "建议", "text": "x"*2001}]}
        collector = C.GenerationStream(conversation())
        self.assertEqual(collector.feed(json.dumps(data)), [])
        with self.assertRaises(ValueError):
            C.parse_generation(json.dumps(data), conversation())


class DelayedHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def handle(self):
        try:
            super().handle()
        except ConnectionError:
            # Cancellation deliberately closes keep-alive connections in tests.
            pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.payloads.append(payload)
        if not payload.get("stream"):
            body = json.dumps({"choices": [{"message": {"content": FULL}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def write_event(part, finish=None):
            body = ("data: " + json.dumps({"choices": [{"delta": {"content": part},
                          "finish_reason": finish}]}, ensure_ascii=False) + "\n\n").encode()
            self.wfile.write(("%X\r\n" % len(body)).encode() + body + b"\r\n")
            self.wfile.flush()
        try:
            model = payload["model"]
            write_event(self.server.prefixes.get(model, PREFIX))
            self.server.first_sent.set()
            (self.server.backup_release if model == "backup" else self.server.release).wait(4)
            if model in self.server.truncate_models:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
                return
            write_event(self.server.tails.get(model, TAIL), "stop")
            done = b"data: [DONE]\n\n"
            self.wfile.write(("%X\r\n" % len(done)).encode() + done + b"\r\n0\r\n\r\n")
            self.wfile.flush()
        except (ConnectionError, OSError):
            pass

    def log_message(self, *args):
        pass


class StreamUITests(unittest.TestCase):
    def setUp(self):
        gc.collect()  # Reclaim old Tk fixtures on their owning main thread.
        self.logs = patch.object(core, "log")
        self.log = self.logs.start()
        self.app = BuddyApp(core, copy.deepcopy(core.DEFAULT_CFG), "fake-key", testing=True)
        c = conversation()
        self.app.sessions.append(c)
        self.app.activate(c)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), DelayedHandler)
        self.server.daemon_threads = True
        self.server.release = threading.Event()
        self.server.backup_release = threading.Event()
        self.server.truncate_models = set()
        self.server.prefixes = {}
        self.server.tails = {}
        self.server.first_sent = threading.Event()
        self.server.payloads = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.app.cfg.update(api_base="http://127.0.0.1:%d/v1" % self.server.server_port,
                            model="synthetic-model", fallback_models=[], stream_responses=True)

    def tearDown(self):
        self.server.release.set()
        self.server.backup_release.set()
        self.app.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(1)
        end = time.monotonic()+1
        while time.monotonic() < end:
            first = core._http_slots.acquire(blocking=False)
            second = first and core._http_slots.acquire(blocking=False)
            if second:
                core._http_slots.release()
            if first:
                core._http_slots.release()
            if second:
                break
            time.sleep(0.005)
        self.logs.stop()
        while True:
            try:
                _, session = core._http_sessions.get_nowait()
                session.close()
            except queue.Empty:
                break
        self.app = None
        gc.collect()

    def pump_until(self, predicate, timeout=2):
        end = time.monotonic()+timeout
        while time.monotonic() < end:
            while True:
                try:
                    self.app.handle_event(*self.app.q.get_nowait())
                except queue.Empty:
                    break
            self.app.root.update()
            if predicate():
                return
            time.sleep(0.005)
        self.fail("expected streaming state did not arrive")

    def preview(self):
        self.app.start("generate")
        self.pump_until(lambda: self.app.preview_active)
        return self.app.epoch

    def test_real_sse_first_reply_can_copy_before_tail_then_completes_with_one_request(self):
        a = self.app
        started = time.monotonic()
        self.preview()
        self.assertLess(time.monotonic()-started, 1)
        self.assertTrue(a.busy)
        self.assertFalse(self.server.release.is_set())
        self.assertEqual(a.cards, [FIRST])
        self.assertIn("需要确认数量吗", a.result["question"])
        self.assertEqual(len(self.server.payloads), 1)
        self.assertTrue(all(m["content"][0]["type"] == "text" for m in self.server.payloads[0]["messages"][1:]))
        copy_button = next(b for b in a.controls if b.cget("text") == "复制")
        edit_button = next(b for b in a.controls if b.cget("text") == "编辑")
        self.assertEqual(str(copy_button.cget("state")), "normal")
        self.assertEqual(str(edit_button.cget("state")), "disabled")
        a.root.deiconify()
        a.root.geometry("500x620")
        a.root.update()
        self.assertLess(copy_button.winfo_rooty()+copy_button.winfo_height(), a.status_row.winfo_rooty())
        with patch.object(a.root, "clipboard_clear"), patch.object(a.root, "clipboard_append") as copied:
            copy_button.invoke()
            copied.assert_called_once_with(FIRST["text"])
        self.server.release.set()
        self.pump_until(lambda: not a.busy)
        self.assertEqual(a.cards, [FIRST, SECOND])
        self.assertFalse(a.preview_active)
        self.assertEqual(len(self.server.payloads), 1)
        logged = [args[0] for args, _ in self.log.call_args_list]
        self.assertTrue(any("first_usable=" in line for line in logged))
        self.assertTrue(any("阶段=生成" in line and "headers=" in line and "first_content=" in line for line in logged))
        self.assertTrue(any("流程阶段=生成 prepare=" in line for line in logged))
        self.assertFalse(any("fake-key" in line or FIRST["text"] in line for line in logged))

    def test_cancel_and_late_stream_cannot_reintroduce_or_copy_candidate(self):
        a = self.app
        old_job = self.preview()
        basis = a.current_reply_basis()
        a.cancel()
        a.handle_event(old_job, "partial", ({"cards": [FIRST], "question": "", "facts": []}, basis))
        self.assertEqual(a.cards, [])
        with patch.object(a.root, "clipboard_append") as copied:
            a.copy_card(0)
            copied.assert_not_called()
        self.server.release.set()
        self.assertFalse(a.busy)

    def test_context_change_rejects_preview_and_copy(self):
        a = self.app
        self.preview()
        a.active.edit(a.active.messages[-1]["id"], "self", "这是我说的")
        with patch.object(a.root, "clipboard_append") as copied:
            a.copy_card(0)
            copied.assert_not_called()
        old_cards = copy.deepcopy(a.cards)
        a.handle_event(a.epoch, "partial", ({"cards": [SECOND]}, a.reply_basis))
        self.assertEqual(a.cards, old_cards)

    def test_failure_clears_partial_and_retry_does_not_repeat_capture(self):
        a = self.app
        self.server.truncate_models.add(a.cfg["model"])
        self.preview()
        self.server.release.set()
        self.pump_until(lambda: not a.busy)
        self.assertEqual(a.cards, [])
        self.assertFalse(a.preview_active)
        self.assertEqual(a.last_retry[0], "generate")
        self.assertIn("已撤下", a.status.cget("text"))
        a.cfg["stream_responses"] = False
        a.retry()
        self.pump_until(lambda: not a.busy)
        self.assertEqual(a.cards, [FIRST, SECOND])
        self.assertEqual(len(self.server.payloads), 2)
        self.assertTrue(all(item["type"] == "text" for payload in self.server.payloads
                            for message in payload["messages"][1:] for item in message["content"]))

    def test_fallback_attempt_resets_preview_instead_of_mixing_cards(self):
        a = self.app
        a.cfg["fallback_models"] = ["backup"]
        self.server.truncate_models.add(a.cfg["model"])
        self.server.prefixes["backup"] = '{"question":"","candidates":[' + json.dumps(SECOND)
        self.server.tails["backup"] = '],"situation":"","facts":[]}'
        self.preview()
        self.server.release.set()
        self.pump_until(lambda: a.cards == [SECOND])
        self.assertTrue(a.busy)
        self.assertEqual(a.cards, [SECOND])
        self.server.backup_release.set()
        self.pump_until(lambda: not a.busy)
        self.assertEqual(a.cards, [SECOND])
        self.assertEqual([p["model"] for p in self.server.payloads], ["synthetic-model", "backup"])

    def test_non_streaming_json_still_returns_full_reply_and_timing(self):
        a = self.app
        a.cfg["stream_responses"] = False
        a.start("generate")
        self.pump_until(lambda: not a.busy)
        self.assertEqual(a.cards, [FIRST, SECOND])
        self.assertFalse(a.preview_active)

    def test_unknown_identity_still_blocks_before_http_request(self):
        a = self.app
        a.active.edit(a.active.messages[-1]["id"], "unknown", "身份待确认")
        a.start("generate")
        self.assertFalse(a.busy)
        self.assertEqual(self.server.payloads, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
