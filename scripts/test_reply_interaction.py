"""Local UI regression for compact replies, inline editing and reversible roles."""
import copy
import os
import sys
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import buddy_context as C
import wx_helper as core
from buddy_ui import BuddyApp


class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.log = patch.object(core, "log")
        self.log.start()
        self.app = BuddyApp(core, copy.deepcopy(core.DEFAULT_CFG), "dummy", testing=True)
        c = C.Conversation("小林")
        c.ingest(C.pasted_messages("对方：这周能帮忙吗？\n我：这次具体要做什么？\n对方：明天下午要用。"))
        self.app.sessions.append(c)
        self.app.activate(c)
        self.replies()

    def tearDown(self):
        self.app.close()
        self.log.stop()

    def replies(self):
        self.app.handle_event(self.app.epoch, "generated", {
            "cards": [{"label": "问清范围", "text": "具体需要做几张？"}, {"label": "暂缓表态", "text": "我先看看内容。"}],
            "situation": "先确认范围。", "question": "", "facts": []})
        self.app.root.update()

    def change_editor(self, value):
        self.app.inline_editor.delete("1.0", "end")
        self.app.inline_editor.insert("1.0", value)

    def test_generated_reply_collapses_recent_messages_keeps_identity_and_precedes_settings(self):
        a = self.app
        a.root.deiconify()
        a.root.geometry("500x620")
        a.root.update()
        self.assertEqual(a.recent_box.winfo_manager(), "")
        self.assertIn("小林", a.contact_label.cget("text"))
        self.assertEqual(a.target_role_button.cget("text"), "对方")
        self.assertIn("明天下午要用", a.last_message.cget("text"))
        self.assertLess(a.card_box.winfo_y(), a.plan_panel.winfo_y())
        label = a.card_labels[0]
        self.assertTrue(label.winfo_ismapped())
        self.assertLess(label.winfo_rooty()+label.winfo_height(), a.status_row.winfo_rooty())
        a.toggle_recent()
        self.assertEqual(a.recent_box.winfo_manager(), "pack")
        a.toggle_recent()
        self.assertEqual(a.recent_box.winfo_manager(), "")

    def test_copy_inline_edit_saves_selected_reply_without_dialog_or_network(self):
        a = self.app
        with patch.object(core, "call_model") as call, patch.object(a.root, "clipboard_clear"), \
             patch.object(a.root, "clipboard_append") as clipboard:
            a.show_edit(1)
            self.assertIsNone(a.root.grab_current())
            self.assertEqual(a.inline_editor.winfo_toplevel(), a.root)
            self.change_editor("你先发给我看看吧。")
            next(b for b in a.controls if b.cget("text") == "复制").invoke()
            clipboard.assert_called_once_with("你先发给我看看吧。")
            call.assert_not_called()
        self.assertEqual(a.cards[1]["text"], "你先发给我看看吧。")
        self.assertEqual(a.cards[0]["text"], "具体需要做几张？")
        self.assertIsNone(a.editing_index)

    def test_cancel_edit_restores_original_and_empty_draft_does_not_copy(self):
        a = self.app
        a.show_edit(0)
        self.change_editor("")
        with patch.object(a.root, "clipboard_append") as clipboard:
            a.copy_card(0)
            clipboard.assert_not_called()
        self.assertIsNotNone(a.inline_editor)
        self.assertEqual(a.cards[0]["text"], "具体需要做几张？")
        a.cancel_edit()
        self.assertIsNone(a.inline_editor)
        self.assertEqual(a.cards[0]["text"], "具体需要做几张？")

    def test_switch_direction_saves_draft_and_rerender_does_not_drop_it(self):
        a = self.app
        a.show_edit(0)
        self.change_editor("先给我一个范围吧。")
        a.render_cards()
        self.assertEqual(a.inline_editor.get("1.0", "end-1c"), "先给我一个范围吧。")
        with patch("buddy_ui.threading.Thread"):
            a.choose_direction(1)
        self.assertEqual(a.cards[0]["text"], "先给我一个范围吧。")
        self.assertIsNone(a.editing_index)
        a.cancel()
        self.assertEqual(a.card_labels[0].cget("text"), "先给我一个范围吧。")

    def test_cached_read_restores_edited_reply_and_preserves_compact_view(self):
        a = self.app
        a.show_edit(0)
        self.change_editor("我先看具体内容。")
        with patch("buddy_ui.threading.Thread"):
            a.start("read")
        self.assertEqual(a.read_restore["cards"][0]["text"], "我先看具体内容。")
        a.handle_event(a.epoch, "reused", a.active.id)
        self.assertEqual(a.cards[0]["text"], "我先看具体内容。")
        self.assertEqual(a.recent_box.winfo_manager(), "")

    def test_identity_menu_changes_and_undo_restores_message_and_explicit_target(self):
        a = self.app
        c = a.active
        mid = c.messages[-1]["id"]
        a.select_target(mid)
        self.replies()
        before = copy.deepcopy(c.messages[-1])
        with patch.object(tk.Menu, "tk_popup"), patch.object(core, "call_model") as call:
            a.target_role_menu()
            a.role_menu.invoke(0)
            self.assertEqual(c.messages[-1]["role"], "self")
            self.assertEqual(a.cards, [])
            self.assertIsNone(c.target_id)
            self.assertTrue(a.can_undo_correction())
            revision = c.revision
            a.undo_button.invoke()
            self.assertEqual(c.messages[-1], before)
            self.assertEqual(c.target_id, mid)
            self.assertTrue(c.explicit_target)
            self.assertGreater(c.revision, revision)
            self.assertFalse(a.can_undo_correction())
            call.assert_not_called()

    def test_group_identity_keeps_actual_nickname_across_toggle_and_undo(self):
        a = self.app
        c = C.Conversation("项目群", "群聊")
        c.ingest(C.pasted_messages("小赵：明天下午开会。"))
        a.activate(c)
        mid = c.messages[0]["id"]
        a.correct_role(mid, "self")
        self.assertEqual(c.messages[0]["sender"], "小赵")
        a.undo_correction()
        self.assertEqual(c.messages[0]["role"], "other")
        self.assertEqual(c.messages[0]["sender"], "小赵")
        self.assertEqual(a.target_role_button.cget("text"), "小赵")

    def test_unknown_role_blocks_generation_and_undo_reenables_original_role(self):
        a = self.app
        mid = a.active.messages[-1]["id"]
        a.correct_role(mid, "unknown")
        with patch.object(core, "call_model") as call:
            a.start("generate")
            call.assert_not_called()
        self.assertIn("发送者", a.active.guard())
        a.undo_correction()
        self.assertEqual(a.active.guard(), "")

    def test_undo_does_not_override_new_target_and_cannot_cross_sessions(self):
        a = self.app
        c = a.active
        mid = c.messages[-1]["id"]
        a.correct_role(mid, "self")
        first = c.messages[0]["id"]
        a.select_target(first)
        a.undo_correction()
        self.assertEqual(c.target_id, first)
        a.correct_role(mid, "self")
        other = C.Conversation("小赵")
        a.activate(other)
        a.undo_correction()
        self.assertEqual(c.messages[-1]["role"], "self")
        self.assertFalse(a.can_undo_correction())

    def test_stale_menu_owner_and_busy_editor_cannot_mutate_state(self):
        a = self.app
        first = a.active
        mid = first.messages[-1]["id"]
        a.activate(C.Conversation("小赵"))
        a.correct_role(mid, "self", first)
        self.assertEqual(first.messages[-1]["role"], "other")
        a.activate(first)
        self.replies()
        a.show_edit(0)
        a.set_busy(True)
        self.assertEqual(a.inline_editor.cget("state"), "disabled")
        a.correct_role(mid, "self")
        self.assertEqual(first.messages[-1]["role"], "other")

    def test_new_messages_expire_undo_and_original_text_edit_can_be_undone(self):
        a = self.app
        c = a.active
        mid = c.messages[-1]["id"]
        before = copy.deepcopy(c.messages[-1])
        a.edit_message(mid)
        top = a.root.grab_current()
        stack, widgets = [top], []
        while stack:
            w = stack.pop()
            widgets.append(w)
            stack.extend(w.winfo_children())
        text = next(w for w in widgets if isinstance(w, tk.Text))
        text.delete("1.0", "end")
        text.insert("1.0", "我纠正的原话")
        next(w for w in widgets if isinstance(w, tk.Button) and w.cget("text") == "保存纠正").invoke()
        self.assertEqual(c.messages[-1]["text"], "我纠正的原话")
        a.undo_correction()
        self.assertEqual(c.messages[-1], before)
        a.correct_role(mid, "self")
        c.ingest(C.pasted_messages("对方：后来的新消息"), force=True)
        self.assertFalse(a.can_undo_correction())


if __name__ == "__main__":
    unittest.main(verbosity=2)
