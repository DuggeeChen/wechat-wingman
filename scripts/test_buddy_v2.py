"""Offline regression: evidence, ownership, UI workflow, deadlines and cancellation."""
import copy
import json
import os
import sys
import threading
import time
import unittest
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch, Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import buddy_context as C
import wx_helper as core
from buddy_ui import BuddyApp


def msg(text, role="other", sender=""):
    return {"id": C.uid(), "text": text, "role": role, "sender": sender, "source": "测试", "corrected": False}


def capture(name="小林", role="other", side="left", kind="单聊", sender=""):
    return json.dumps({"name": name, "kind": kind, "messages": [
        {"role": role, "side": side, "bbox": [0.2, 0.2, 0.7, 0.3], "sender": sender, "text": "明天下午能帮我看看吗？"}]}, ensure_ascii=False)


class EvidenceTests(unittest.TestCase):
    def test_spatial_disagreement_stays_unknown(self):
        self.assertEqual(C.parse_capture(capture(role="self"))["messages"][0]["role"], "unknown")

    def test_missing_bbox_stays_unknown(self):
        data = json.loads(capture())
        del data["messages"][0]["bbox"]
        self.assertEqual(C.parse_capture(json.dumps(data))["messages"][0]["role"], "unknown")

    def test_bbox_on_opposite_side_rejected(self):
        data = json.loads(capture())
        data["messages"][0]["bbox"] = [0.8, 0.2, 0.9, 0.3]
        self.assertEqual(C.parse_capture(json.dumps(data))["messages"][0]["role"], "unknown")

    def test_group_sender_required(self):
        self.assertEqual(C.parse_capture(capture(kind="群聊"))["messages"][0]["role"], "unknown")
        self.assertEqual(C.parse_capture(capture(kind="群聊", sender="小李"))["messages"][0]["sender"], "小李")

    def test_no_conversation_and_invalid_json(self):
        for text in (capture(name=""), "not json", "[]"):
            with self.assertRaises(ValueError):
                C.parse_capture(text)

    def test_append_overlap_preserves_ids(self):
        c = C.Conversation("林")
        c.ingest([msg("先说具体的需求"), msg("我看看工作量", "self"), msg("需要做五张海报")])
        old = c.messages[-2]["id"]
        outcome = c.ingest([msg("我看看工作量", "self"), msg("需要做五张海报"), msg("明天下午之前")])
        self.assertEqual(outcome, "merged")
        self.assertEqual(len(c.messages), 4)
        self.assertEqual(c.messages[1]["id"], old)

    def test_prepend_preserves_latest_target(self):
        c = C.Conversation("林")
        c.ingest([msg("我看看工作量", "self"), msg("需要做五张海报"), msg("明天下午之前")])
        target = c.target_id
        c.ingest([msg("先说具体的需求"), msg("我看看工作量", "self"), msg("需要做五张海报")], older=True)
        self.assertEqual(c.messages[0]["text"], "先说具体的需求")
        self.assertEqual(c.target_id, target)

    def test_same_screenshot_no_duplicates(self):
        c = C.Conversation("林")
        c.ingest([msg("你好"), msg("最近如何")])
        self.assertEqual(c.ingest(copy.deepcopy(c.messages)), "same")
        self.assertEqual(len(c.messages), 2)

    def test_single_ack_never_auto_joins(self):
        c = C.Conversation("林")
        c.ingest([msg("好的")])
        self.assertEqual(c.ingest([msg("好的"), msg("下次再聊")]), "pending")
        self.assertEqual(len(c.messages), 1)
        self.assertTrue(c.guard())

    def test_repeated_anchors_are_ambiguous(self):
        c = C.Conversation("林")
        c.ingest([msg("请发具体内容"), msg("发给你了", "self"), msg("请发具体内容"), msg("发给你了", "self")])
        self.assertEqual(c.ingest([msg("请发具体内容"), msg("发给你了", "self"), msg("明天见")]), "pending")

    def test_gap_requires_explicit_order(self):
        c = C.Conversation("林")
        c.ingest([msg("新消息")])
        c.ingest([msg("旧消息")], older=True)
        self.assertEqual(len(c.messages), 1)
        c.ingest(c.pending["messages"], older=True, force=True)
        self.assertEqual([m["text"] for m in c.messages], ["旧消息", "新消息"])
        self.assertEqual(len(c.gaps), 1)
        self.assertIsNone(c.pending)

    def test_self_last_waits(self):
        c = C.Conversation("林")
        c.ingest([msg("明天下午呢"), msg("三点可以", "self")])
        self.assertIsNone(c.target_id)
        self.assertIn("你已回复", c.guard())
        c.target_id = c.messages[-1]["id"]
        c.explicit_target = True
        self.assertEqual(c.guard(), "")

    def test_unknown_recent_message_blocks(self):
        c = C.Conversation("林")
        c.ingest([msg("不确定是谁说的", "unknown"), msg("好的")])
        self.assertIn("发送者", c.guard())
        c.edit(c.messages[0]["id"], "self", "不确定是谁说的")
        self.assertEqual(c.guard(), "")
        self.assertTrue(c.messages[0]["corrected"])

    def test_manual_input_does_not_guess(self):
        messages = C.pasted_messages("我：先确认范围\n对方：做五张海报\n没有身份的一句\n小赵：明天交")
        self.assertEqual([m["role"] for m in messages], ["self", "other", "unknown", "other"])
        self.assertEqual(messages[3]["sender"], "小赵")

    def test_background_separate_from_evidence(self):
        c = C.Conversation("林")
        c.ingest([msg("这次能帮忙吗")])
        c.background = "之前已拒绝过一次"
        c.goal, c.boundary = "维持关系", "不答应帮忙"
        data = c.payload()
        self.assertEqual(data["user_background"], c.background)
        self.assertNotIn(c.background, str(data["messages"]))
        prompt = C.generation_prompt(c, "默认")
        self.assertIn(c.boundary, prompt)

    def test_history_bound_disclosed_and_old_target_included(self):
        c = C.Conversation("林")
        c.ingest([msg("消息%d" % i) for i in range(140)])
        c.target_id = c.messages[0]["id"]
        p = c.payload()
        self.assertEqual(p["omitted_message_count"], 39)
        self.assertEqual(p["messages"][0]["id"], c.target_id)

    def test_fabricated_evidence_ids_rejected(self):
        c = C.Conversation("林")
        c.ingest([msg("周五给你答复")])
        result = C.parse_generation(json.dumps({"candidates": [{"text": "好，等你消息"}], "facts": [
            {"text": "周五回复", "evidence_ids": [c.messages[0]["id"]]},
            {"text": "已经承诺付款", "evidence_ids": ["invented"]}]}), c)
        self.assertEqual(len(result["facts"]), 1)

    def test_malformed_candidates_rejected(self):
        for value in ([], {}, "abc", None):
            with self.assertRaises(ValueError):
                C.parse_generation(json.dumps({"candidates": value}), C.Conversation("林"))


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.cfg = copy.deepcopy(core.DEFAULT_CFG)
        self.log = patch.object(core, "log")
        self.log.start()

    def tearDown(self):
        self.log.stop()

    def test_connect_and_read_timeout_are_different(self):
        for error, expected in ((core.requests.ConnectTimeout(), "连接服务超时"), (core.requests.ReadTimeout(), "等待模型返回超时")):
            with patch.object(core.requests.Session, "post", side_effect=error):
                _, err = core.call_model(self.cfg, "dummy", None, "hello")
                self.assertIn(expected, err)

    def test_total_deadline_bounds_wait(self):
        release = threading.Event()
        def post(*a, **kw):
            release.wait(2)
            raise core.requests.ReadTimeout()
        with patch.object(core.requests.Session, "post", side_effect=post):
            start = time.monotonic()
            # _bounded_post exercises an active request past its outer deadline.
            _, error = core._bounded_post("url", {}, {}, (1, 1), start+0.15, None)
            self.assertEqual(error, "deadline")
            self.assertLess(time.monotonic()-start, 0.6)
            release.set()
        time.sleep(0.02)

    def test_cancel_drops_inflight_result(self):
        release, cancel = threading.Event(), threading.Event()
        def post(*a, **kw):
            cancel.set()
            release.wait(2)
            raise core.requests.ReadTimeout()
        with patch.object(core.requests.Session, "post", side_effect=post):
            _, error = core._bounded_post("url", {}, {}, (1, 1), time.monotonic()+3, cancel)
            self.assertEqual(error, "cancel")
            release.set()
        time.sleep(0.02)

    def test_success_and_no_auth_retry(self):
        response = Mock(status_code=200)
        response.headers = {"Content-Type": "application/json"}
        response.json.return_value = {"choices": [{"message": {"content": "OK"}}]}
        with patch.object(core.requests.Session, "post", return_value=response):
            self.assertEqual(core.call_model(self.cfg, "dummy", None, "hello"), ("OK", None))
        response.status_code = 401
        self.cfg["fallback_models"] = ["backup"]
        with patch.object(core.requests.Session, "post", return_value=response) as post:
            self.assertIn("401", core.call_model(self.cfg, "dummy", None, "hello")[1])
            self.assertEqual(post.call_count, 1)

    def test_streamed_chinese_response(self):
        response = Mock(status_code=200)
        response.headers = {"Content-Type": "text/event-stream"}
        response.iter_lines.return_value = [
            b": heartbeat", b"", ("data: " + json.dumps({"choices": [{"delta": {"content": "你好"}}]}, ensure_ascii=False)).encode("utf-8"),
            b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}', b'data: [DONE]']
        with patch.object(core.requests.Session, "post", return_value=response):
            self.assertEqual(core.call_model(self.cfg, "dummy", None, "hello"), ("你好", None))

    def test_incomplete_stream_not_accepted(self):
        response = Mock(status_code=200)
        response.headers = {"Content-Type": "text/event-stream"}
        response.iter_lines.return_value = [b'data: {"choices":[{"delta":{"content":"partial"}}]}']
        with patch.object(core.requests.Session, "post", return_value=response):
            self.assertIn("返回格式异常", core.call_model(self.cfg, "dummy", None, "hello")[1])

    def test_configured_fallback_after_read_timeout(self):
        self.cfg["fallback_models"] = ["backup"]
        response = Mock(status_code=200, headers={"Content-Type": "application/json"})
        response.json.return_value = {"choices": [{"message": {"content": "backup result"}}]}
        with patch.object(core.requests.Session, "post", side_effect=[core.requests.ReadTimeout(), response]) as post:
            self.assertEqual(core.call_model(self.cfg, "dummy", None, "hello"), ("backup result", None))
            self.assertEqual(post.call_args_list[0].kwargs["json"]["model"], self.cfg["model"])
            self.assertEqual(post.call_args_list[1].kwargs["json"]["model"], "backup")


class UITests(unittest.TestCase):
    def setUp(self):
        self.log = patch.object(core, "log")
        self.log.start()
        self.app = BuddyApp(core, copy.deepcopy(core.DEFAULT_CFG), "dummy", testing=True)
        self.app.root.update()

    def tearDown(self):
        self.app.close()
        self.log.stop()

    def fill(self):
        self.app.accept_capture(C.parse_capture(capture()))

    def test_read_does_not_generate(self):
        with patch.object(core, "find_wechat", return_value=("ok", 1)), patch.object(core, "capture_wechat", return_value=core.Image.new("RGB", (640, 480))), \
             patch.object(core, "crop_chat", return_value=object()), patch.object(core, "to_jpeg_b64", return_value="image"), \
             patch.object(core, "call_model", return_value=(capture(), None)) as call:
            self.app.worker(0, threading.Event(), "read", {"cfg": self.app.cfg})
            job, kind, result = self.app.q.get_nowait()
            self.assertEqual(kind, "capture")
            self.app.handle_event(job, kind, result)
            self.assertEqual(len(self.app.active.messages), 1)
            self.assertEqual(self.app.cards, [])
            self.assertEqual(call.call_count, 1)

    def test_failed_generation_keeps_context(self):
        self.fill()
        ident = self.app.active.id
        self.app.handle_event(self.app.epoch, "error", "等待模型返回超时")
        self.assertEqual(self.app.active.id, ident)
        self.assertEqual(len(self.app.active.messages), 1)

    def test_unknown_blocks_network(self):
        self.app.accept_capture(C.parse_capture(capture(role="unknown")))
        with patch.object(core, "call_model") as call:
            self.app.start("generate")
            self.assertFalse(self.app.busy)
            call.assert_not_called()

    def test_different_contact_not_auto_merged(self):
        self.fill()
        with patch.object(self.app, "resolve_pending"):
            self.app.accept_capture(C.parse_capture(capture(name="小赵")))
        self.assertEqual(self.app.active.name, "小林")
        self.assertIsNotNone(self.app.pending_capture)
        self.assertEqual(len(self.app.active.messages), 1)

    def test_sessions_isolate_plans(self):
        self.fill()
        first = self.app.active
        self.app.goal.set("维持关系")
        self.app.boundary.set("不答应")
        self.app.plan_changed()
        second = C.Conversation("小赵")
        self.app.activate(second)
        self.assertEqual(self.app.goal.get(), "")
        self.assertEqual(self.app.boundary.get(), "")
        self.app.activate(first)
        self.assertEqual(self.app.boundary.get(), "不答应")

    def test_changing_plan_invalidates_cards(self):
        self.fill()
        self.app.cards = [{"text": "可以", "label": "答应"}]
        self.app.goal.set("拒绝")
        self.app.plan_changed()
        self.assertEqual(self.app.cards, [])

    def test_direction_switch_reuses_cards_without_network_or_plan_change(self):
        self.fill()
        a = self.app
        a.cards = [{"text": "具体有几张？", "label": "问清范围"}, {"text": "这次帮不上，抱歉。", "label": "婉拒"}]
        a.render_cards()
        with patch("buddy_ui.threading.Thread") as thread:
            a.choose_direction(1)
            self.assertFalse(a.busy)
            self.assertEqual(a.card_labels[0].cget("text"), "这次帮不上，抱歉。")
            a.choose_direction(0)
            self.assertEqual(a.card_labels[0].cget("text"), "具体有几张？")
            thread.assert_not_called()
        self.assertEqual((a.active.goal, a.active.boundary), ("", ""))
        self.assertEqual(a.selected_card, 0)

    def test_collapsed_requirements_remain_applied_and_clear_invalidates(self):
        self.fill()
        a = self.app
        self.assertEqual(a.requirements_box.winfo_manager(), "")
        a.toggle_requirements()
        a.goal.set("维持关系")
        a.boundary.set("不承诺交付时间")
        a.plan_changed()
        a.toggle_requirements()
        self.assertEqual(a.requirements_box.winfo_manager(), "")
        self.assertIn("已设置", a.requirements_button.cget("text"))
        self.assertEqual(a.active.payload()["boundary"], "不承诺交付时间")
        a.cards = [{"text": "旧建议", "label": "旧"}]
        a.clear_requirements()
        self.assertEqual(a.cards, [])
        self.assertEqual((a.active.goal, a.active.boundary), ("", ""))
        self.assertNotIn("已设置", a.requirements_button.cget("text"))

    def test_session_switch_collapses_requirements_and_resets_direction(self):
        self.fill()
        a = self.app
        first = a.active
        a.boundary.set("不答应")
        a.plan_changed()
        a.toggle_requirements()
        a.selected_card = 2
        a.activate(C.Conversation("另一个人"))
        self.assertFalse(a.requirements_open)
        self.assertEqual(a.selected_card, 0)
        self.assertNotIn("已设置", a.requirements_button.cget("text"))
        a.activate(first)
        self.assertIn("已设置", a.requirements_button.cget("text"))

    def test_late_cancelled_result_ignored(self):
        self.fill()
        job = self.app.epoch
        self.app.cancel()
        self.app.handle_event(job, "generated", {"cards": [{"text": "旧结果", "label": "旧"}]})
        self.assertEqual(self.app.cards, [])

    def test_primary_controls_fit_minimum_height(self):
        a = self.app
        a.root.deiconify()
        a.root.geometry("500x620")
        a.root.update()
        for b in (a.go_button, a.more_button):
            self.assertTrue(b.winfo_ismapped())
            self.assertLessEqual(b.winfo_rooty()-a.root.winfo_rooty()+b.winfo_height(), a.root.winfo_height())

    def test_draft_dialog_does_not_send_on_open(self):
        self.fill()
        with patch.object(core, "call_model") as call:
            self.app.check_draft("我先看看具体范围")
            self.app.root.update()
            call.assert_not_called()
            self.assertTrue(self.app.draft_input.winfo_exists())

    def test_correction_dialog_can_save(self):
        self.fill()
        self.app.cards = [{"label": "旧", "text": "旧建议"}]
        self.app.edit_message(self.app.active.messages[0]["id"])
        self.app.root.update()
        top = self.app.root.grab_current()
        stack, widgets = [top], []
        while stack:
            w = stack.pop()
            widgets.append(w)
            stack.extend(w.winfo_children())
        combo = next(w for w in widgets if isinstance(w, ttk.Combobox))
        combo.set("我")
        button = next(w for w in widgets if isinstance(w, tk.Button) and w.cget("text") == "保存纠正")
        button.invoke()
        self.assertEqual(self.app.active.messages[0]["role"], "self")
        self.assertEqual(self.app.cards, [])
        self.assertIsNone(self.app.active.target_id)

    def test_background_saved_separately(self):
        self.fill()
        self.app.show_context()
        self.app.root.update()
        top = self.app.root.grab_current()
        stack, widgets = [top], []
        while stack:
            w = stack.pop()
            widgets.append(w)
            stack.extend(w.winfo_children())
        notebook = next(w for w in widgets if isinstance(w, ttk.Notebook))
        page = self.app.root.nametowidget(notebook.tabs()[0])
        text = next(w for w in page.winfo_children() if isinstance(w, tk.Text))
        text.insert("1.0", "上周已经拒绝过一次")
        button = next(w for w in widgets if isinstance(w, tk.Button) and w.cget("text") == "保存前情")
        button.invoke()
        self.assertEqual(self.app.active.background, "上周已经拒绝过一次")
        self.assertEqual(len(self.app.active.messages), 1)


class SetupTests(unittest.TestCase):
    def test_footer_visible_across_scaling(self):
        from setup_wizard import SetupWizard
        for scale in (1.0, 1.5, 2.0):
            w = SetupWizard({}, lambda _cfg: True)
            original_scale = w.root.tk.call("tk", "scaling")
            try:
                w.root.tk.call("tk", "scaling", scale)
                w.root.update()
                stack, buttons = [w.root], []
                while stack:
                    widget = stack.pop()
                    stack.extend(widget.winfo_children())
                    if isinstance(widget, tk.Button):
                        buttons.append(widget)
                save = next(b for b in buttons if b.cget("text") == "保存并开始")
                self.assertTrue(save.winfo_ismapped())
                self.assertLessEqual(save.winfo_rooty()-w.root.winfo_rooty()+save.winfo_height(), w.root.winfo_height())
            finally:
                # Tk scaling persists across roots within one test process.
                w.root.tk.call("tk", "scaling", original_scale)
                w.cancel()
            self.assertFalse(w.saved)


if __name__ == "__main__":
    unittest.main(verbosity=2)
