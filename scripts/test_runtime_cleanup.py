"""Cleanup boundaries and the actual menu action, using disposable local fixtures."""
import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import buddy_context as C
import runtime_cleanup as R
import wx_helper as core
from buddy_ui import BuddyApp


class FileCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_only_three_disposable_files_removed_while_private_and_program_files_preserved(self):
        for name in R.TEMP_NAMES:
            (self.root / name).write_bytes(b"temporary")
        retained = {"config.json": b'{"model":"user-model"}', "ui_state.json": b"window",
                    "assets/icon.png": b"icon", "profiles/person.json": b"history",
                    ".upgrades/old/wx_helper.py": b"backup", "user-photo.png": b"photo",
                    "notes.log": b"not-an-app-log", ".env": b"not-for-cleanup"}
        for name, data in retained.items():
            file = self.root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
        result = R.clean_temporary_data(self.root)
        self.assertEqual(set(result["removed"]), set(R.TEMP_NAMES))
        self.assertEqual(result["bytes"], 27)
        self.assertEqual(result["failed"], [])
        for name, data in retained.items():
            self.assertEqual((self.root / name).read_bytes(), data)

    def test_missing_files_and_repeated_cleanup_do_nothing(self):
        expected = {"removed": [], "bytes": 0, "failed": []}
        self.assertEqual(R.clean_temporary_data(self.root), expected)
        self.assertEqual(R.clean_temporary_data(self.root), expected)

    def test_directory_with_disposable_name_is_never_recursively_deleted(self):
        path = self.root / "debug_last.png"
        path.mkdir()
        (path / "keep.txt").write_text("keep", encoding="utf-8")
        result = R.clean_temporary_data(self.root)
        self.assertEqual(result["failed"], ["debug_last.png"])
        self.assertEqual((path / "keep.txt").read_text(), "keep")

    def test_locked_file_is_reported_and_other_files_can_still_be_removed(self):
        for name in R.TEMP_NAMES:
            (self.root / name).write_text("fixture", encoding="utf-8")
        unlink = Path.unlink
        def selective(path, *args, **kwargs):
            if path.name == "wx_helper.log":
                raise PermissionError("synthetic locked file")
            return unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", selective):
            result = R.clean_temporary_data(self.root)
        self.assertEqual(result["failed"], ["wx_helper.log"])
        self.assertTrue((self.root / "wx_helper.log").exists())
        self.assertEqual(len(result["removed"]), 2)

    def test_resolved_path_outside_data_dir_is_not_deleted(self):
        path = self.root / "debug_last.png"
        path.write_text("fixture", encoding="utf-8")
        resolve = Path.resolve
        def outside(value, *args, **kwargs):
            return self.root.parent / "outside.png" if value.name == "debug_last.png" else resolve(value, *args, **kwargs)
        with patch.object(Path, "resolve", outside):
            result = R.clean_temporary_data(self.root)
        self.assertEqual(result["failed"], ["debug_last.png"])
        self.assertTrue(path.exists())

    def test_link_is_left_untouched(self):
        path = self.root / "debug_last.png"
        path.write_text("fixture", encoding="utf-8")
        with patch.object(Path, "is_symlink", return_value=True):
            result = R.clean_temporary_data(self.root)
        self.assertEqual(result["failed"], ["debug_last.png"])
        self.assertTrue(path.exists())


class CleanupUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.logs = patch.object(core, "log")
        self.logs.start()
        self.app = BuddyApp(core, copy.deepcopy(core.DEFAULT_CFG), "dummy", testing=True)
        c = C.Conversation("虚构联系人")
        c.ingest(C.pasted_messages("对方：能帮忙看看吗？"))
        c.background = "虚构前情"
        self.app.sessions.append(c)
        self.app.activate(c)
        self.app.handle_event(self.app.epoch, "generated", {"cards": [{"label": "问清楚", "text": "具体是哪一部分？"}],
                              "situation": "", "question": "", "facts": []})
        self.app.capture_cache = {"key": "fake-fingerprint", "session_id": c.id}

    def tearDown(self):
        self.app.close()
        self.logs.stop()
        self.temp.cleanup()

    def test_menu_action_preserves_chat_and_settings_and_does_not_call_a_model(self):
        a = self.app
        before_cfg = copy.deepcopy(a.cfg)
        c, cards, basis = a.active, copy.deepcopy(a.cards), a.reply_basis
        path = Path(self.temp.name)
        (path / "wx_helper.log").write_text("fixture", encoding="utf-8")
        with patch("buddy_ui.tk.Menu.tk_popup"), patch.object(core, "DATA_DIR", self.temp.name), \
             patch.object(core, "call_model") as call:
            a.open_menu()
            menus = [w for w in a.root.winfo_children() if w.winfo_class() == "Menu"]
            menu = menus[-1]
            index = next(i for i in range(menu.index("end")+1)
                         if menu.type(i) == "command" and menu.entrycget(i, "label") == "清理截图与临时数据")
            menu.invoke(index)
            call.assert_not_called()
        self.assertFalse((path / "wx_helper.log").exists())
        self.assertIsNone(a.capture_cache)
        self.assertIs(a.active, c)
        self.assertEqual(c.background, "虚构前情")
        self.assertEqual(a.cfg, before_cfg)
        self.assertEqual(a.cards, cards)
        self.assertEqual(a.reply_basis, basis)
        self.assertIn("已清理", a.status.cget("text"))

    def test_busy_or_modal_state_never_cleans_files_or_invalidates_cache(self):
        a = self.app
        with patch("runtime_cleanup.clean_temporary_data") as clean:
            a.set_busy(True)
            a.clear_temporary_data()
            a.set_busy(False)
            with patch.object(a.root, "grab_current", return_value=object()):
                a.clear_temporary_data()
            clean.assert_not_called()
        self.assertIsNotNone(a.capture_cache)

    def test_failure_message_does_not_claim_all_files_were_removed(self):
        a = self.app
        with patch("runtime_cleanup.clean_temporary_data", return_value={"removed": [], "bytes": 0, "failed": ["wx_helper.log"]}):
            a.clear_temporary_data()
        self.assertIn("未能清理", a.status.cget("text"))
        self.assertIsNone(a.capture_cache)

    def test_inline_draft_is_saved_and_empty_edit_prevents_cleanup(self):
        a = self.app
        with patch("runtime_cleanup.clean_temporary_data", return_value={"removed": [], "bytes": 0, "failed": []}) as clean:
            a.show_edit(0)
            a.inline_editor.delete("1.0", "end")
            a.clear_temporary_data()
            clean.assert_not_called()
            a.inline_editor.insert("1.0", "你先发我看看吧。")
            a.clear_temporary_data()
            clean.assert_called_once()
        self.assertEqual(a.cards[0]["text"], "你先发我看看吧。")


if __name__ == "__main__":
    unittest.main(verbosity=2)
