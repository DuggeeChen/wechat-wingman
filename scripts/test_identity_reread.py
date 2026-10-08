"""Speaker uncertainty diagnostics and exact-frame refresh. Fictional data only."""
import copy
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import buddy_context as C
import wx_helper as core
import test_fast_workflow as fast


def capture(items=None, name="虚构联系人"):
    items = items or [{"text": "虚构消息", "role": "other", "side": "left", "bbox": [.2, .2, .6, .3]}]
    return json.dumps({"name": name, "kind": "单聊", "messages": items}, ensure_ascii=False)


def uncertain():
    return capture([{"text": "虚构消息", "role": "other", "side": "left"}])


class IdentityReasonTests(unittest.TestCase):
    def test_distinct_missing_invalid_and_model_uncertain_reasons(self):
        rows = [(None, "other", "left", "missing_bbox"), ([.2, .2, 20, .3], "other", "left", "invalid_bbox"),
                ([.2, .2, .6, .3], "unknown", "unknown", "uncertain")]
        for box, role, side, expected in rows:
            item = {"text": "虚构文字", "role": role, "side": side, "bbox": box}
            message = C.parse_capture(capture([item]))["messages"][0]
            self.assertEqual((message["role"], message["identity_reason"]), ("unknown", expected))
            self.assertTrue(C.identity_reason_text(message))

    def test_role_side_conflict_and_geometric_conflict_remain_unknown(self):
        self.assertEqual(C.capture_identity({"role": "self", "side": "left", "bbox": [.2, .2, .6, .3]}, "单聊"), ("unknown", "conflict"))
        self.assertEqual(C.capture_identity({"role": "other", "side": "left", "bbox": [.8, .2, .9, .3]}, "单聊"), ("unknown", "geometry"))

    def test_group_nickname_requirement_remains(self):
        item = {"role": "other", "side": "left", "bbox": [.2, .2, .6, .3]}
        self.assertEqual(C.capture_identity(item, "群聊"), ("unknown", "group_sender"))

    def test_manual_and_unlabeled_reasons(self):
        message = C.pasted_messages("没有标注发送者的虚构文字")[0]
        self.assertEqual(message["identity_reason"], "unlabeled")
        self.assertIn("粘贴", C.identity_reason_text(message))
        message["corrected"] = True
        self.assertIn("你暂时", C.identity_reason_text(message))

    def test_quote_content_does_not_change_outer_sender(self):
        item = {"role": "other", "side": "left", "bbox": [.13, .86, .78, .94], "text": "虚构回应\n引用：我：虚构原话"}
        self.assertEqual(C.parse_capture(capture([item]))["messages"][0]["role"], "other")

    def test_diagnostic_codes_are_not_sent_in_generation_context(self):
        c = C.Conversation("虚构联系人")
        c.ingest(C.parse_capture(uncertain())["messages"])
        self.assertNotIn("identity_reason", json.dumps(c.payload()))


class IdentityRefreshTests(unittest.TestCase):
    def setUp(self):
        self.c = C.Conversation("虚构联系人")
        self.c.ingest(C.parse_capture(uncertain())["messages"])
        self.ids = [m["id"] for m in self.c.messages]
        self.incoming = C.parse_capture(capture())["messages"]

    def test_refresh_updates_only_identity_preserving_id_text_and_count(self):
        old_id, revision = self.ids[0], self.c.revision
        self.assertTrue(self.c.needs_identity_refresh(self.ids))
        self.assertEqual(self.c.refresh_identities(self.incoming, self.ids), 1)
        self.assertEqual(len(self.c.messages), 1)
        self.assertEqual(self.c.messages[0]["id"], old_id)
        self.assertEqual(self.c.target_id, old_id)
        self.assertEqual(self.c.revision, revision+1)
        self.assertFalse(self.c.needs_identity_refresh(self.ids))

    def test_changed_text_or_count_is_rejected_without_mutation(self):
        before = copy.deepcopy(self.c.messages)
        for incoming in ([], [dict(self.incoming[0], text="另一条不同文字")]):
            with self.assertRaises(ValueError):
                self.c.refresh_identities(incoming, self.ids)
            self.assertEqual(self.c.messages, before)

    def test_duplicate_or_missing_ids_cannot_refresh(self):
        for ids in (["missing"], self.ids*2):
            with self.assertRaises(ValueError):
                self.c.refresh_identities(self.incoming, ids)

    def test_same_text_on_different_messages_only_refreshes_cached_id(self):
        extra = copy.deepcopy(self.c.messages[0]); extra["id"] = C.uid()
        self.c.messages.insert(0, extra)
        self.c.refresh_identities(self.incoming, self.ids)
        self.assertEqual([m["role"] for m in self.c.messages], ["unknown", "other"])

    def test_identical_text_twice_in_cached_frame_is_ambiguous(self):
        extra = copy.deepcopy(self.c.messages[0]); extra["id"] = C.uid()
        self.c.messages.append(extra)
        before = copy.deepcopy(self.c.messages)
        with self.assertRaisesRegex(ValueError, "重复原文"):
            self.c.refresh_identities(self.incoming*2, [m["id"] for m in self.c.messages])
        self.assertEqual(self.c.messages, before)

    def test_manual_correction_and_deliberate_unknown_are_preserved(self):
        for role in ("self", "unknown"):
            self.c.edit(self.ids[0], role, "用户修改过的正文")
            before = copy.deepcopy(self.c.messages)
            self.assertFalse(self.c.needs_identity_refresh(self.ids))
            self.assertEqual(self.c.refresh_identities(self.incoming, self.ids), 0)
            self.assertEqual(self.c.messages, before)

    def test_already_known_sender_cannot_be_overwritten(self):
        self.c.messages[0]["role"] = "self"
        self.assertEqual(self.c.refresh_identities(self.incoming, self.ids), 0)
        self.assertEqual(self.c.messages[0]["role"], "self")

    def test_pasted_unknown_cannot_be_resolved_from_screenshot(self):
        self.c.messages[0]["source"] = "手动粘贴"
        self.assertFalse(self.c.needs_identity_refresh(self.ids))
        self.assertEqual(self.c.refresh_identities(self.incoming, self.ids), 0)

    def test_explicit_target_survives_refresh(self):
        self.c.target_id, self.c.explicit_target = self.ids[0], True
        self.c.refresh_identities(self.incoming, self.ids)
        self.assertTrue(self.c.explicit_target)
        self.assertEqual(self.c.target_id, self.ids[0])

    def test_still_uncertain_stays_guarded_without_revision_change(self):
        revision = self.c.revision
        self.assertEqual(self.c.refresh_identities(C.parse_capture(uncertain())["messages"], self.ids), 0)
        self.assertEqual(self.c.revision, revision)
        self.assertTrue(self.c.guard())


class RereadWorkflowTests(unittest.TestCase):
    setUp = fast.WorkflowTests.setUp
    tearDown = fast.WorkflowTests.tearDown
    run_mode = fast.WorkflowTests.run_mode

    def first_uncertain(self, mode="read"):
        with patch.object(core, "call_model", return_value=(uncertain(), None)) as model:
            self.run_mode(mode)
            self.assertEqual(model.call_count, 1)
        return self.app.active.messages[0]["id"]

    def test_identical_frame_with_unknown_is_reread_not_cached_or_duplicated(self):
        mid = self.first_uncertain()
        with patch.object(core, "call_model", return_value=(capture(), None)) as model:
            self.run_mode("read")
            self.assertEqual(model.call_count, 1)
        self.assertEqual(len(self.app.active.messages), 1)
        self.assertEqual(self.app.active.messages[0]["id"], mid)
        self.assertEqual(self.app.active.messages[0]["role"], "other")
        self.assertIsNone(self.app.active.pending)
        with patch.object(core, "call_model") as model:
            self.run_mode("read")
            model.assert_not_called()

    def test_read_generate_refreshes_then_generates_once(self):
        self.first_uncertain("read_generate")
        with patch.object(core, "call_model", side_effect=[(capture(), None), (fast.REPLY, None)]) as model:
            self.run_mode("read_generate")
            self.assertEqual(model.call_count, 2)
            self.assertTrue(model.call_args_list[0].args[2])
            self.assertIsNone(model.call_args_list[1].args[2])
        self.assertTrue(self.app.cards)

    def test_still_unknown_does_not_loop_or_generate(self):
        self.first_uncertain()
        with patch.object(core, "call_model", return_value=(uncertain(), None)) as model:
            self.run_mode("read_generate")
            self.assertEqual(model.call_count, 1)
        self.assertFalse(self.app.cards)
        self.assertIn("气泡位置", self.app.last_message.cget("text"))

    def test_corrected_unknown_retains_cache_and_manual_text(self):
        mid = self.first_uncertain()
        self.app.active.edit(mid, "unknown", "手动修正的原文")
        with patch.object(core, "call_model") as model:
            self.run_mode("read")
            model.assert_not_called()
        self.assertEqual(self.app.active.messages[0]["text"], "手动修正的原文")

    def test_mismatching_contact_is_rejected_without_merging(self):
        self.first_uncertain()
        before = copy.deepcopy(self.app.active.messages)
        with patch.object(core, "call_model", return_value=(capture(name="另一位虚构联系人"), None)):
            self.run_mode("read")
        self.assertEqual(self.app.active.messages, before)
        self.assertIn("聊天对象不一致", self.app.status.cget("text"))

    def test_unknown_reason_visible_in_identity_menu(self):
        mid = self.first_uncertain()
        with patch("tkinter.Menu.tk_popup"):
            self.app.show_role_menu(mid, self.app.more_button)
        self.assertIn("气泡位置", self.app.role_menu.entrycget(0, "label"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
