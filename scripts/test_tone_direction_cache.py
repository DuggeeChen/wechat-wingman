"""Cached direction selection, explicit rewrites, and actual voice transport."""
import copy
import json
import os
import queue
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import buddy_context as C
import tone_styles
import wx_helper as core
from test_direction_reply import DirectionFixture, CARDS, NEW, output
from test_streaming_reply import DelayedHandler


class CachedDirectionsTests(DirectionFixture, unittest.TestCase):
    def test_click_there_and_back_or_same_direction_uses_no_request(self):
        a = self.app
        with patch.object(core, "call_model") as call, patch("buddy_ui.threading.Thread") as thread:
            for index in (1, 2, 0, 2, 2, 1, 0):
                a.choose_direction(index)
                self.assertEqual(a.card_labels[0].cget("text"), CARDS[index]["text"])
                self.assertFalse(a.busy)
            call.assert_not_called()
            thread.assert_not_called()

    def test_switching_back_reuses_latest_rewrite_and_edited_text(self):
        a = self.app
        with patch.object(core, "call_model", return_value=(output(), None)) as call:
            a.rewrite_direction(1)
            self.pump()
            self.assertEqual(call.call_count, 1)
        with patch.object(core, "call_model") as call:
            a.choose_direction(0)
            a.choose_direction(1)
            self.assertEqual(a.card_labels[0].cget("text"), NEW["text"])
            a.show_edit(1)
            a.inline_editor.delete("1.0", "end")
            a.inline_editor.insert("1.0", "我自己改好的回复。")
            a.choose_direction(2)
            a.choose_direction(1)
            self.assertEqual(a.cards[1]["text"], "我自己改好的回复。")
            call.assert_not_called()

    def test_explicit_card_button_rewrites_just_one_direction(self):
        a = self.app
        a.choose_direction(1)
        with patch.object(core, "call_model", return_value=(output(), None)) as call:
            next(b for b in a.controls if b.cget("text") == "换一条").invoke()
            self.pump()
        self.assertEqual(call.call_count, 1)
        self.assertIsNone(call.call_args.args[2])
        self.assertEqual(a.cards, [CARDS[0], NEW, CARDS[2]])
        self.assertIn("direction_context", call.call_args.args[3])

    def test_style_change_and_context_change_cannot_reuse_stale_direction(self):
        a = self.app
        a.cfg["personas"][a.persona.get()] = "新的写作要求"
        with patch.object(core, "call_model") as call:
            a.choose_direction(1)
            self.assertEqual(a.cards, [])
            call.assert_not_called()

    def test_restore_one_version_does_not_erase_other_card_edits(self):
        a = self.app
        with patch.object(core, "call_model", return_value=(output(), None)):
            a.rewrite_direction(1)
            self.pump()
        a.cards[2]["text"] = "另一条手工修改。"
        a.previous_direction()
        self.assertEqual(a.cards[1], CARDS[1])
        self.assertEqual(a.cards[2]["text"], "另一条手工修改。")
        self.assertEqual(a.selected_card, 1)

    def test_restore_button_only_refers_to_the_rewritten_direction(self):
        a = self.app
        with patch.object(core, "call_model", return_value=(output(), None)):
            a.rewrite_direction(1)
            self.pump()
        a.choose_direction(2)
        self.assertFalse(any(b.cget("text") == "恢复这条回复的上一版" for b in a.controls))
        a.previous_direction()
        self.assertEqual(a.cards[1], NEW)
        a.choose_direction(1)
        self.assertTrue(any(b.cget("text") == "恢复这条回复的上一版" for b in a.controls))

    def test_updated_style_definition_is_sent_as_system_instruction_with_current_name(self):
        a = self.app
        a.cfg["personas"]["我自己的风格"] = "简练但有温度，表达先感谢再商量。"
        a.persona.set("我自己的风格")
        a.persona_changed()
        with patch.object(core, "call_model", return_value=(output(), None)) as call:
            a.start("generate")
            self.pump()
        system = call.call_args.kwargs["system"]
        self.assertIn("我自己的风格", system)
        self.assertIn("简练但有温度，表达先感谢再商量。", system)
        self.assertIn("不是聊天原话", system)
        self.assertEqual((a.active.goal, a.active.boundary), ("", ""))

    def test_same_definition_different_style_names_have_different_reply_basis(self):
        a = self.app
        style = a.cfg["personas"][a.persona.get()]
        original = a.current_reply_basis()
        a.cfg["personas"]["新名称"] = style
        a.persona.set("新名称")
        self.assertNotEqual(a.current_reply_basis(), original)

    def test_editing_selected_style_in_library_invalidates_cached_cards_on_close(self):
        a = self.app
        top = tk.Toplevel(a.root)
        with patch.object(core, "open_style_editor", return_value=top):
            a.open_styles()
        a.cfg["personas"][a.persona.get()] = "风格库修改后的要求。"
        top.destroy()
        self.assertEqual(a.cards, [])
        self.assertIn("风格库已更新", a.status.cget("text"))

    def test_unrelated_style_edit_does_not_discard_current_cards(self):
        a = self.app
        top = tk.Toplevel(a.root)
        with patch.object(core, "open_style_editor", return_value=top):
            a.open_styles()
        a.cfg["personas"]["另一种风格"] = "另外一个自定义要求。"
        top.destroy()
        self.assertEqual(a.cards, CARDS)

    def test_direction_intent_is_retained_when_rewrite_response_omits_it(self):
        a = self.app
        a.cards[1]["intent"] = "礼貌拒绝而不增加承诺"
        with patch.object(core, "call_model", return_value=(output(), None)) as call:
            a.rewrite_direction(1)
            self.pump()
        self.assertIn("礼貌拒绝而不增加承诺", call.call_args.args[3])
        self.assertEqual(a.cards[1]["intent"], "礼貌拒绝而不增加承诺")


class VoiceContractsTests(unittest.TestCase):
    def test_exact_original_defaults_upgrade_but_custom_edits_names_and_blanks_survive(self):
        styles = dict(tone_styles.LEGACY_STYLES)
        styles.update(商务="我自己写的商务要求", 客套="", 新风格="随意聊天")
        upgraded = tone_styles.upgrade_builtin_styles(styles)
        self.assertEqual(upgraded["默认"], tone_styles.DEFAULT_STYLES["默认"])
        self.assertEqual(upgraded["商务"], "我自己写的商务要求")
        self.assertEqual(upgraded["客套"], "")
        self.assertEqual(upgraded["新风格"], "随意聊天")
        self.assertEqual(styles["默认"], tone_styles.LEGACY_STYLES["默认"])

    def test_loading_original_library_upgrades_in_memory_without_writing_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            cfg = copy.deepcopy(core.DEFAULT_CFG)
            cfg["personas"] = dict(tone_styles.LEGACY_STYLES)
            path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
            before = path.read_bytes()
            with patch.object(core, "CFG_PATH", str(path)):
                loaded = core.load_cfg()
            self.assertEqual(loaded["personas"], tone_styles.DEFAULT_STYLES)
            self.assertEqual(path.read_bytes(), before)

    def test_rewrites_with_tiny_word_changes_are_not_reported_as_new_content(self):
        old = "你先把这次海报的内容和数量发给我，我看过后再确认时间。"
        new = "你先把这次海报的内容和数量发给我，我看完后再确认时间。"
        with self.assertRaises(ValueError):
            C.direction_result({"cards": [{"label": "确认范围", "text": new}]}, "确认范围", [old])

    def test_different_short_replies_are_not_rejected_for_a_shared_word(self):
        result = {"cards": [{"label": "说明", "text": "我先看看内容。"}]}
        self.assertEqual(C.direction_result(result, "说明", ["我先确认时间。"])["cards"], result["cards"])

    def test_duplicate_initial_candidates_are_not_three_fake_directions(self):
        c = C.Conversation("虚构联系人")
        c.ingest(C.pasted_messages("对方：能帮忙看看吗？"))
        data = {"question": "", "candidates": [{"label": "回应", "text": "先发我看看。", "intent": "先了解具体内容"},
                {"label": "了解", "text": "先发我看看！"}, {"label": "询问", "text": "是哪个部分出了问题？", "intent": "缩小问题范围"}], "facts": []}
        text = json.dumps(data, ensure_ascii=False)
        full = C.parse_generation(text, c)
        self.assertEqual(len(full["cards"]), 2)
        self.assertEqual(full["cards"][0]["intent"], "先了解具体内容")
        stream = C.GenerationStream(c)
        updates = stream.feed(text)
        self.assertEqual([len(r["cards"]) for r in updates], [1, 2])
        self.assertEqual(updates[-1]["cards"], full["cards"])


class VoiceTransportTests(DirectionFixture, unittest.TestCase):
    def test_real_loopback_http_receives_voice_in_system_separate_from_chat(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), DelayedHandler)
        server.daemon_threads = True
        server.payloads = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        a = self.app
        a.cfg.update(api_base="http://127.0.0.1:%d/v1" % server.server_port, fallback_models=[], stream_responses=False)
        a.cfg["personas"]["亲密"] = tone_styles.DEFAULT_STYLES["亲密"]
        a.persona.set("亲密")
        a.persona_changed()
        try:
            a.start("generate")
            self.pump()
            payload = server.payloads[0]
            self.assertEqual(len(server.payloads), 1)
            self.assertEqual(payload["messages"][0]["role"], "system")
            self.assertIn(tone_styles.DEFAULT_STYLES["亲密"], payload["messages"][0]["content"])
            self.assertNotIn("能帮我做海报吗？", payload["messages"][0]["content"])
            self.assertIn("能帮我做海报吗？", payload["messages"][1]["content"][0]["text"])
        finally:
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
