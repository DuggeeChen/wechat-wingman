"""Offline settings tests: provider isolation, atomic saving and actual UI actions."""
import copy
import json
import os
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import model_settings as M
import wx_helper as core
from buddy_ui import BuddyApp


class SettingsFixture:
    def setUp(self):
        self.cfg = copy.deepcopy(core.DEFAULT_CFG)
        self.cfg.update(api_base="https://old.example/v1", model="old-model", api_credential_target="old-target",
                        fallback_models=["old-backup"])
        self.store = {"old-target": "old-key"}
        self.patches = [patch.object(M.credentials, "read_secret", side_effect=lambda target: self.store.get(target, "")),
                        patch.object(M.credentials, "write_secret", side_effect=lambda target, key, comment: self.store.update({target: key})),
                        patch.object(M.credentials, "delete_secret", side_effect=lambda target: self.store.pop(target, None)),
                        patch.object(core, "log")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()


class SettingsTests(SettingsFixture, unittest.TestCase):
    def test_normalize_full_endpoint(self):
        self.assertEqual(M.normalize_base(" https://NEW.example/v1/chat/completions/ "), "https://new.example/v1")

    def test_wrong_urls_are_rejected(self):
        for url in ("foo", "https://example/v1?key=private", "https://user:pass@example/v1", "https://example/v1/messages", "https://{WorkspaceId}.example/v1"):
            with self.assertRaises(ValueError):
                M.normalize_base(url)

    def test_never_reuse_old_key_at_new_provider(self):
        with self.assertRaises(ValueError):
            M.resolve_key(self.cfg, "https://new.example/v1", current_key="old-key")

    def test_current_key_preserved_at_same_provider(self):
        self.assertEqual(M.resolve_key(self.cfg, self.cfg["api_base"], current_key="runtime-key"), "runtime-key")

    def test_failed_config_save_does_not_rotate_active_secret(self):
        before = copy.deepcopy(self.cfg)
        with self.assertRaises(ValueError):
            M.commit_connection(self.cfg, self.cfg["api_base"], "new-model", "rotated-key", "old-key", M.CUSTOM, lambda _cfg: False)
        self.assertEqual(self.cfg, before)
        self.assertEqual(self.store, {"old-target": "old-key"})

    def test_switch_saves_no_secret_and_clears_old_fallbacks(self):
        saved = []
        key = M.commit_connection(self.cfg, "https://new.example/v1", "new-model", "new-key", "old-key", M.CUSTOM,
                                  lambda cfg: saved.append(copy.deepcopy(cfg)) or True)
        self.assertEqual(key, "new-key")
        self.assertEqual(self.cfg["fallback_models"], [])
        self.assertEqual(self.cfg["api_key_source"], "credential")
        self.assertFalse(self.cfg["send_reasoning_effort"])
        self.assertNotIn("new-key", json.dumps(saved))
        self.assertNotIn("old-key", json.dumps(saved))
        self.assertEqual(self.store["old-target"], "old-key")

    def test_return_to_previous_provider_without_reentering_key(self):
        M.commit_connection(self.cfg, "https://new.example/v1", "new-model", "new-key", "old-key", M.CUSTOM, lambda _cfg: True)
        self.assertEqual(M.resolve_key(self.cfg, "https://old.example/v1", current_key="new-key"), "old-key")
        self.assertEqual(M.connection_for(self.cfg, "https://old.example/v1")["model"], "old-model")

    def test_model_only_change_reuses_current_secret(self):
        M.commit_connection(self.cfg, self.cfg["api_base"], "other-model", "", "old-key", M.CUSTOM, lambda _cfg: True)
        self.assertEqual(self.store, {"old-target": "old-key"})
        self.assertEqual(self.cfg["model"], "other-model")

    def test_explicit_credentials_override_environment(self):
        self.cfg["api_key_source"] = "credential"
        with patch.dict(os.environ, {self.cfg["api_key_env"]: "wrong-provider-key"}):
            self.assertEqual(core.load_key(self.cfg), "old-key")

    def test_no_environment_fallback_after_managed_key_missing(self):
        self.cfg.update(api_key_source="credential", api_credential_target="missing")
        with patch.dict(os.environ, {self.cfg["api_key_env"]: "wrong-provider-key"}):
            with self.assertRaises(SystemExit):
                core.load_key(self.cfg)

    def test_fetch_models_sorted_and_deduplicated(self):
        response = Mock()
        response.json.return_value = {"data": [{"id": "b"}, {"id": "a"}, {"id": "a"}]}
        import requests
        with patch.object(requests, "get", return_value=response) as get:
            self.assertEqual(M.fetch_models(self.cfg["api_base"], "old-key"), ["a", "b"])
            self.assertEqual(get.call_args.args[0], "https://old.example/v1/models")
            response.close.assert_called_once()

    def test_connection_uses_synthetic_image_and_only_selected_model(self):
        with patch.object(core, "call_model", return_value=("蓝色", None)) as call:
            self.assertIn("通过", M.test_connection(core, self.cfg, "https://new.example/v1", "new-model", "new-key",
                                                {"send_reasoning_effort": False}))
            args = call.call_args.args
            self.assertEqual(args[0]["fallback_models"], [])
            self.assertEqual(args[0]["model"], "new-model")
            self.assertTrue(args[2])
            self.assertNotIn("聊天", args[3])

    def test_failed_vision_probe_not_reported_as_success(self):
        with patch.object(core, "call_model", return_value=("红色", None)):
            with self.assertRaises(ValueError):
                M.test_connection(core, self.cfg, self.cfg["api_base"], "model", "old-key")

    def test_standard_payload_omits_extra_reasoning_field(self):
        cfg = copy.deepcopy(self.cfg)
        cfg.update(send_reasoning_effort=False, token_limit_field="max_completion_tokens", stream_responses=False)
        response = Mock(status_code=200, headers={"Content-Type": "application/json"})
        response.json.return_value = {"choices": [{"message": {"content": "OK"}}]}
        with patch.object(core.requests.Session, "post", return_value=response) as post:
            core.call_model(cfg, "dummy", None, "hello")
            payload = post.call_args.kwargs["json"]
            self.assertNotIn("reasoning_effort", payload)
            self.assertNotIn("max_tokens", payload)
            self.assertIn("max_completion_tokens", payload)
            self.assertFalse(payload["stream"])


class SettingsUITests(SettingsFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.app = BuddyApp(core, self.cfg, "old-key", testing=True)
        self.app.root.deiconify()
        self.app.root.update()
        self.app.open_model_settings()
        self.app.root.update()
        self.editor = self.app.model_settings

    def tearDown(self):
        if not self.editor.closed:
            self.editor.close()
        self.app.close()
        super().tearDown()

    def test_save_applies_immediately_and_preserves_conversation(self):
        import buddy_context as C
        conversation = C.Conversation("林")
        conversation.ingest(C.pasted_messages("对方：你好"))
        conversation.background = "前情"
        self.app.active = conversation
        self.app.cards = [{"text": "old", "label": "old"}]
        self.editor.base.set("https://new.example/v1")
        self.editor.model.set("new-model")
        self.editor.secret.set("new-key")
        with patch.object(core, "save_cfg", return_value=True) as save:
            self.editor.save()
            save.assert_called_once()
        self.assertTrue(self.editor.closed)
        self.assertEqual(self.app.key, "new-key")
        self.assertEqual(self.app.cfg["model"], "new-model")
        self.assertIs(self.app.active, conversation)
        self.assertEqual(self.app.active.background, "前情")
        self.assertEqual(self.app.cards, [])

    def test_cancel_leaves_config_unchanged(self):
        old = copy.deepcopy(self.cfg)
        self.editor.base.set("https://new.example/v1")
        self.editor.secret.set("new-key")
        self.editor.close()
        self.assertEqual(self.cfg, old)
        self.assertEqual(self.store, {"old-target": "old-key"})

    def test_provider_selection_updates_base_and_never_reveals_key(self):
        self.editor.provider.set("硅基流动（中国）")
        self.editor.provider_changed()
        self.assertEqual(self.editor.base.get(), "https://api.siliconflow.cn/v1")
        self.assertEqual(self.editor.secret.get(), "")
        self.assertEqual(self.editor.model.get(), "")
        self.assertFalse(self.editor.reasoning.get())

    def test_endpoint_edit_clears_entered_secret(self):
        self.editor.secret.set("old-key")
        self.editor.base.set("https://new.example/v1")
        self.assertEqual(self.editor.secret.get(), "")

    def test_save_button_visible_at_minimum_size(self):
        self.editor.top.geometry("570x620")
        self.app.root.update()
        b = self.editor.save_button
        self.assertTrue(b.winfo_ismapped())
        self.assertLessEqual(b.winfo_rooty()-self.editor.top.winfo_rooty()+b.winfo_height(), self.editor.top.winfo_height())

    def test_late_async_result_ignored_after_close(self):
        self.editor.results.put((self.editor.job, "models", ["late-model"], None))
        self.editor.close()
        self.editor.poll()
        self.assertEqual(self.cfg["model"], "old-model")


if __name__ == "__main__":
    unittest.main(verbosity=2)
