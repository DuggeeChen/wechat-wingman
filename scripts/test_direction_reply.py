"""Targeted direction regeneration: real UI events and synthetic loopback SSE."""
import copy
import gc
import json
import os
import queue
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import buddy_context as C
import wx_helper as core
from buddy_ui import BuddyApp
from test_streaming_reply import DelayedHandler
from http.server import ThreadingHTTPServer

CARDS = [{"label": "确认范围", "text": "具体需要做几张？"},
         {"label": "婉拒", "text": "这次帮不上，抱歉。"},
         {"label": "暂缓表态", "text": "我先看看具体内容。"}]
NEW = {"label": "婉拒", "text": "我现在腾不出时间，建议你先找其他人。"}


def output(card=NEW):
    return json.dumps({"question": "", "candidates": [card], "situation": "按所选方向回答", "facts": []}, ensure_ascii=False)


class DirectionPromptTests(unittest.TestCase):
    def test_selected_direction_is_data_and_specific_generation_rule_not_draft_or_goal(self):
        c = C.Conversation("虚构联系人")
        c.ingest(C.pasted_messages("对方：能帮我做海报吗？"))
        text = C.generation_prompt(c, "简短", [v["text"] for v in CARDS], direction="婉拒")
        self.assertIn('"requested_direction": "婉拒"', text)
        self.assertIn("只给 1 条", text)
        self.assertIn('"draft": null', text)
        self.assertEqual((c.goal, c.boundary), ("", ""))

    def test_duplicate_reply_reordered_or_only_punctuation_changes_is_rejected(self):
        for text in (CARDS[0]["text"], CARDS[2]["text"], "具体需要做几张!!!", "具体 需要做几张"):
            with self.assertRaises(ValueError):
                C.direction_result({"cards": [{"label": "新标题", "text": text}]}, "婉拒", [c["text"] for c in CARDS])

    def test_new_text_preserves_requested_label_and_does_not_modify_input(self):
        result = {"cards": [{"label": "不同的标题", "text": NEW["text"]}], "facts": []}
        changed = C.direction_result(result, "婉拒", [c["text"] for c in CARDS])
        self.assertEqual(changed["cards"], [NEW])
        self.assertEqual(result["cards"][0]["label"], "不同的标题")


class DirectionFixture:
    def setUp(self):
        gc.collect()
        self.log = patch.object(core, "log")
        self.log.start()
        self.app = BuddyApp(core, copy.deepcopy(core.DEFAULT_CFG), "fake-key", testing=True)
        c = C.Conversation("虚构联系人")
        c.ingest(C.pasted_messages("对方：能帮我做海报吗？"))
        self.app.activate(c)
        self.app.cards = copy.deepcopy(CARDS)
        self.app.result = {"cards": copy.deepcopy(CARDS), "question": "", "facts": []}
        self.app.reply_basis = self.app.current_reply_basis()
        self.app.render_cards()

    def tearDown(self):
        self.app.close()
        self.log.stop()
        gc.collect()

    def pump(self):
        end = time.monotonic()+3
        while self.app.busy and time.monotonic() < end:
            try:
                self.app.handle_event(*self.app.q.get_nowait())
            except queue.Empty:
                time.sleep(0.005)
            self.app.root.update()
        self.assertFalse(self.app.busy)

    def begin(self, index=1):
        with patch("buddy_ui.threading.Thread"):
            self.app.rewrite_direction(index)
        return self.app.epoch


class DirectionUiTests(DirectionFixture, unittest.TestCase):
    def test_click_new_reply_uses_one_text_request_and_keeps_other_directions(self):
        a = self.app
        with patch.object(core, "call_model", return_value=(output(), None)) as call, \
             patch.object(core, "find_wechat") as capture, patch.object(core, "grab") as grab:
            a.rewrite_direction(1)
            self.pump()
        self.assertEqual(call.call_count, 1)
        self.assertIsNone(call.call_args.args[2])
        self.assertIn('"requested_direction": "婉拒"', call.call_args.args[3])
        capture.assert_not_called()
        grab.assert_not_called()
        self.assertEqual(a.cards, [CARDS[0], NEW, CARDS[2]])
        self.assertEqual(a.selected_card, 1)
        self.assertEqual(a.card_labels[0].cget("text"), NEW["text"])
        self.assertIsNotNone(a.direction_history)
        self.assertEqual((a.active.goal, a.active.boundary), ("", ""))

    def test_each_direction_and_repeated_same_direction_make_new_requests(self):
        a = self.app
        for n, index in enumerate([0, 1, 2, 2]):
            card = {"label": CARDS[index]["label"], "text": "这是新的回复第%d条。" % n}
            with patch.object(core, "call_model", return_value=(output(card), None)) as call:
                a.rewrite_direction(index)
                self.pump()
                self.assertEqual(call.call_count, 1)
                self.assertEqual(a.cards[index], card)

    def test_old_content_from_another_direction_cannot_be_displayed_as_new(self):
        a = self.app
        with patch.object(core, "call_model", return_value=(output(CARDS[0]), None)):
            a.rewrite_direction(1)
            self.pump()
        self.assertEqual(a.cards, CARDS)
        self.assertIn("重复", a.status.cget("text"))
        self.assertEqual(a.last_retry, ("direction", 1, "婉拒"))

    def test_duplicate_stream_preview_is_suppressed_before_copy(self):
        a = self.app
        def response(*args, **kwargs):
            kwargs["on_delta"](None)
            kwargs["on_delta"](output(CARDS[2]))
            return output(CARDS[2]), None
        with patch.object(core, "call_model", side_effect=response), \
             patch.object(a, "handle_event", wraps=a.handle_event) as events:
            a.rewrite_direction(1)
            self.pump()
        self.assertEqual(a.cards, CARDS)
        self.assertFalse(a.preview_active)
        self.assertFalse(any(c.args[1] == "partial" for c in events.call_args_list))

    def test_cancel_preview_restores_original_and_ignores_late_events(self):
        a = self.app
        job = self.begin()
        basis = a.current_reply_basis()
        a.handle_event(job, "partial", ({"cards": [NEW], "question": "", "facts": []}, basis))
        self.assertEqual(a.cards[1], NEW)
        a.cancel()
        a.handle_event(job, "generated", {"cards": [NEW]})
        a.handle_event(job, "partial", ({"cards": [NEW]}, basis))
        self.assertEqual(a.cards, CARDS)
        self.assertFalse(a.preview_active)
        self.assertIsNone(a.direction_pending)

    def test_error_after_preview_restores_original_and_mentions_copied_text(self):
        a = self.app
        job = self.begin()
        a.handle_event(job, "partial", ({"cards": [NEW]}, a.current_reply_basis()))
        a.handle_event(job, "error", "响应中断")
        self.assertEqual(a.cards, CARDS)
        self.assertIn("如已复制", a.status.cget("text"))

    def test_fallback_preview_reset_restores_original_without_mixing_attempts(self):
        a = self.app
        job = self.begin()
        basis = a.current_reply_basis()
        a.handle_event(job, "partial", ({"cards": [NEW]}, basis))
        a.handle_event(job, "preview_reset", basis)
        self.assertEqual(a.cards, CARDS)
        self.assertFalse(a.preview_active)
        other = dict(NEW, text="抱歉，我这边的时间排不开。")
        a.handle_event(job, "partial", ({"cards": [other]}, basis))
        a.handle_event(job, "generated", {"cards": [other]})
        self.assertEqual(a.cards, [CARDS[0], other, CARDS[2]])

    def test_changed_identity_rejects_late_reply_and_does_not_restore_stale_cards(self):
        a = self.app
        job = self.begin()
        a.active.edit(a.active.messages[-1]["id"], "unknown", "身份待确认")
        a.handle_event(job, "generated", {"cards": [NEW]})
        self.assertEqual(a.cards, [])
        self.assertIsNone(a.direction_pending)
        with patch.object(core, "call_model") as call:
            a.rewrite_direction(1)
            call.assert_not_called()

    def test_restore_last_version_has_no_request_and_preserves_original_order(self):
        a = self.app
        with patch.object(core, "call_model", return_value=(output(), None)):
            a.rewrite_direction(1)
            self.pump()
        with patch.object(core, "call_model") as call:
            a.previous_direction()
            call.assert_not_called()
        self.assertEqual(a.cards, CARDS)
        self.assertEqual(a.selected_card, 1)
        self.assertIsNone(a.direction_history)

    def test_busy_click_does_not_start_second_request(self):
        a = self.app
        job = self.begin()
        with patch("buddy_ui.threading.Thread") as thread:
            a.rewrite_direction(2)
            thread.assert_not_called()
        self.assertEqual(a.epoch, job)
        self.assertEqual(a.selected_card, 1)
        a.cancel()

    def test_edit_is_saved_and_seen_by_selected_direction_request(self):
        a = self.app
        a.show_edit(0)
        a.inline_editor.delete("1.0", "end")
        a.inline_editor.insert("1.0", "我改过的回复。")
        with patch.object(core, "call_model", return_value=(output(), None)) as call:
            a.rewrite_direction(1)
            self.pump()
        self.assertEqual(a.cards[0]["text"], "我改过的回复。")
        self.assertIn("我改过的回复。", call.call_args.args[3])


class DirectionStreamTests(DirectionFixture, unittest.TestCase):
    def test_loopback_first_complete_direction_reply_is_copyable_before_http_tail(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), DelayedHandler)
        server.daemon_threads = True
        server.payloads, server.truncate_models, server.prefixes, server.tails = [], set(), {}, {}
        server.release, server.backup_release, server.first_sent = threading.Event(), threading.Event(), threading.Event()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        a = self.app
        a.cfg.update(api_base="http://127.0.0.1:%d/v1" % server.server_port, model="synthetic-model",
                     fallback_models=[], send_reasoning_effort=False)
        a.reply_basis = a.current_reply_basis()
        server.prefixes["synthetic-model"] = '{"question":"","candidates":[' + json.dumps(NEW)
        server.tails["synthetic-model"] = '],"situation":"","facts":[]}'
        try:
            a.rewrite_direction(1)
            end = time.monotonic()+3
            while not a.preview_active and time.monotonic() < end:
                try:
                    a.handle_event(*a.q.get_nowait())
                except queue.Empty:
                    time.sleep(0.005)
                a.root.update()
            self.assertTrue(a.preview_active)
            self.assertTrue(a.busy)
            self.assertEqual(a.cards, [CARDS[0], NEW, CARDS[2]])
            self.assertEqual(len(server.payloads), 1)
            self.assertTrue(all(p["type"] == "text" for m in server.payloads[0]["messages"][1:] for p in m["content"]))
            with patch.object(a.root, "clipboard_clear"), patch.object(a.root, "clipboard_append") as copied:
                next(b for b in a.controls if b.cget("text") == "复制").invoke()
                copied.assert_called_once_with(NEW["text"])
            self.assertTrue(all(str(b.cget("state")) == "disabled" for b in a.controls if b.cget("text") in [c["label"] for c in CARDS]))
            server.release.set()
            self.pump()
            self.assertEqual(a.cards, [CARDS[0], NEW, CARDS[2]])
            a.root.deiconify()
            a.root.geometry("500x620")
            a.root.update()
            self.assertLessEqual(a.quick_button.winfo_rooty()+a.quick_button.winfo_height(), a.root.winfo_rooty()+a.root.winfo_height())
        finally:
            server.release.set()
            server.backup_release.set()
            end = time.monotonic()+2
            while a.busy and time.monotonic() < end:
                self.pump()
            server.shutdown()
            server.server_close()
            thread.join(1)
            while True:
                try:
                    _, session = core._http_sessions.get_nowait()
                    session.close()
                except queue.Empty:
                    break


if __name__ == "__main__":
    unittest.main(verbosity=2)
