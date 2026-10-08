"""Hidden windows and black-frame regressions. Synthetic pixels, no uploads."""
import copy
import ctypes
import json
import os
import queue
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wx_helper as core
import buddy_context as C
from buddy_ui import BuddyApp


def frame():
    image = core.Image.new("RGB", (640, 480), "white")
    image.paste((50, 130, 70), (220, 180, 450, 260))
    return image


class WindowSelectionTests(unittest.TestCase):
    def select(self, windows, foreground=0):
        def enumerate_windows(callback, unused):
            for hwnd in windows:
                callback(hwnd, 0)
            return 1
        def title(hwnd, buffer, limit):
            buffer.value = "微信"
            return 2
        def rect(hwnd, pointer):
            value = ctypes.cast(pointer, ctypes.POINTER(core.wt.RECT)).contents
            value.left, value.top = 0, 0
            value.right, value.bottom = windows[hwnd][2:]
            return 1
        with patch.object(core.u32, "EnumWindows", side_effect=enumerate_windows), \
             patch.object(core.u32, "GetClassNameW", side_effect=lambda h, b, n: setattr(b, "value", "Qt51514QWindowIcon") or 1), \
             patch.object(core.u32, "GetWindowTextLengthW", return_value=2), \
             patch.object(core.u32, "GetWindowTextW", side_effect=title), \
             patch.object(core, "_window_can_capture", side_effect=lambda h: windows[h][0]), \
             patch.object(core.u32, "IsIconic", side_effect=lambda h: windows[h][1]), \
             patch.object(core.u32, "GetWindowRect", side_effect=rect), \
             patch.object(core.u32, "GetForegroundWindow", return_value=foreground):
            return core.find_wechat()

    def test_hidden_large_window_cannot_override_minimized_visible_window(self):
        self.assertEqual(self.select({1: (False, False, 900, 1300), 2: (True, True, 160, 28)}), ("minimized", None))

    def test_hidden_large_window_cannot_override_open_chat(self):
        self.assertEqual(self.select({1: (False, False, 1800, 1400), 2: (True, False, 680, 480)}), ("ok", 2))

    def test_no_visible_window_reports_none(self):
        self.assertEqual(self.select({1: (False, False, 900, 1300)}), ("none", None))

    def test_foreground_chat_preferred_over_another_larger_chat(self):
        self.assertEqual(self.select({1: (True, False, 1800, 1400), 2: (True, False, 680, 480)}, 2), ("ok", 2))

    def test_cloaked_window_is_unavailable(self):
        def cloaked(hwnd, attr, pointer, size):
            ctypes.cast(pointer, ctypes.POINTER(core.wt.DWORD)).contents.value = 2
            return 0
        with patch.object(core.u32, "IsWindowVisible", return_value=True), \
             patch.object(core._dwm, "DwmGetWindowAttribute", side_effect=cloaked):
            self.assertFalse(core._window_can_capture(1))


class BlackFrameTests(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(core, "log"), patch.object(core, "_window_can_capture", return_value=True),
                        patch.object(core.u32, "IsIconic", return_value=False),
                        patch.object(core.u32, "SetForegroundWindow"), patch.object(core.time, "sleep")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def test_blank_detection_black_white_flat_and_realistic_pixels(self):
        for color in ("black", "white", (22, 22, 22)):
            self.assertTrue(core.capture_is_blank(core.Image.new("RGB", (640, 480), color)))
        self.assertTrue(core.capture_is_blank(None))
        self.assertFalse(core.capture_is_blank(frame()))

    def test_normal_background_capture_does_not_focus_or_capture_screen(self):
        image = frame()
        with patch.object(core, "grab", return_value=image), patch.object(core.ImageGrab, "grab") as screen:
            self.assertIs(core.capture_wechat(1), image)
            core.u32.SetForegroundWindow.assert_not_called()
            screen.assert_not_called()

    def test_black_frame_recovers_with_same_guarded_window_rectangle(self):
        box = (100, 100, 740, 580)
        with patch.object(core, "grab", return_value=core.Image.new("RGB", (640, 480), "black")), \
             patch.object(core, "_visible_capture_rect", return_value=box) as guard, \
             patch.object(core.ImageGrab, "grab", return_value=frame()) as screen:
            self.assertFalse(core.capture_is_blank(core.capture_wechat(7)))
            self.assertEqual(guard.call_count, 2)
            screen.assert_called_once_with(bbox=box, all_screens=True)
            core.u32.SetForegroundWindow.assert_called_once_with(7)

    def test_obstruction_aborts_before_screen_capture(self):
        with patch.object(core, "grab", return_value=None), \
             patch.object(core, "_visible_capture_rect", side_effect=ValueError("遮挡")), \
             patch.object(core.ImageGrab, "grab") as screen:
            with self.assertRaisesRegex(ValueError, "遮挡"):
                core.capture_wechat(1)
            screen.assert_not_called()

    def test_window_move_during_capture_is_rejected(self):
        with patch.object(core, "grab", return_value=None), \
             patch.object(core, "_visible_capture_rect", side_effect=[(0, 0, 640, 480), (1, 0, 641, 480)]), \
             patch.object(core.ImageGrab, "grab", return_value=frame()):
            with self.assertRaisesRegex(ValueError, "发生变化"):
                core.capture_wechat(1)

    def test_both_capture_methods_blank_report_capture_failure(self):
        with patch.object(core, "grab", return_value=None), \
             patch.object(core, "_visible_capture_rect", return_value=(0, 0, 640, 480)), \
             patch.object(core.ImageGrab, "grab", return_value=core.Image.new("RGB", (640, 480), "black")):
            with self.assertRaisesRegex(ValueError, "本次未发送截图"):
                core.capture_wechat(1)

    def test_hidden_window_rejected_before_background_capture(self):
        with patch.object(core, "_window_can_capture", return_value=False), patch.object(core, "grab") as grab:
            with self.assertRaisesRegex(ValueError, "不可见"):
                core.capture_wechat(1)
            grab.assert_not_called()

    def test_cancelled_fallback_does_not_focus_or_capture(self):
        event = threading.Event()
        event.set()
        with patch.object(core, "grab", return_value=None), patch.object(core.ImageGrab, "grab") as screen:
            with self.assertRaisesRegex(ValueError, "取消"):
                core.capture_wechat(1, event)
            screen.assert_not_called()
            core.u32.SetForegroundWindow.assert_not_called()


class CaptureFailureWorkflowTests(unittest.TestCase):
    def test_blank_frame_never_calls_model_or_merges_context(self):
        app = BuddyApp(core, copy.deepcopy(core.DEFAULT_CFG), "fake", testing=True)
        try:
            app.activate(C.Conversation("虚构联系人"))
            app.active.ingest(C.pasted_messages("对方：旧消息"))
            before = copy.deepcopy(app.active.messages)
            with patch.object(core, "find_wechat", return_value=("ok", 7)), \
                 patch.object(core, "capture_wechat", side_effect=ValueError("截图仍是黑屏")), \
                 patch.object(core, "call_model") as model, patch.object(core, "log"):
                app.worker(0, threading.Event(), "read_generate", {"cfg": app.cfg})
                model.assert_not_called()
                self.assertEqual(app.q.get_nowait()[1:], ("error", "截图仍是黑屏"))
            self.assertEqual(app.active.messages, before)
        finally:
            app.close()

    def test_invalid_kind_is_distinguished_from_missing_contact(self):
        with self.assertRaisesRegex(ValueError, "聊天类型未确认"):
            C.parse_capture(json.dumps({"name": "虚构联系人", "kind": "unknown", "messages": []}))


class ForegroundGuardTests(unittest.TestCase):
    def setUp(self):
        def rect(hwnd, pointer):
            value = ctypes.cast(pointer, ctypes.POINTER(core.wt.RECT)).contents
            value.left, value.top, value.right, value.bottom = 100, 100, 740, 580
            return 1
        metrics = {76: 0, 77: 0, 78: 1920, 79: 1080}
        self.patches = [patch.object(core, "_window_can_capture", return_value=True),
                        patch.object(core.u32, "GetForegroundWindow", return_value=7),
                        patch.object(core.u32, "IsIconic", return_value=False),
                        patch.object(core.u32, "GetWindowRect", side_effect=rect),
                        patch.object(core.u32, "GetSystemMetrics", side_effect=metrics.get),
                        patch.object(core.u32, "WindowFromPoint", return_value=7),
                        patch.object(core.u32, "GetAncestor", return_value=7)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def test_visible_same_window_produces_only_its_rectangle(self):
        self.assertEqual(core._visible_capture_rect(7), (100, 100, 740, 580))

    def test_changed_foreground_is_rejected(self):
        with patch.object(core.u32, "GetForegroundWindow", return_value=9):
            with self.assertRaisesRegex(ValueError, "无法切到前台"):
                core._visible_capture_rect(7)

    def test_other_application_covering_chat_is_rejected(self):
        with patch.object(core.u32, "GetAncestor", return_value=9):
            with self.assertRaisesRegex(ValueError, "遮挡"):
                core._visible_capture_rect(7)

    def test_window_partially_outside_screen_is_rejected(self):
        with patch.object(core.u32, "GetSystemMetrics", side_effect={76: 0, 77: 0, 78: 500, 79: 1080}.get):
            with self.assertRaisesRegex(ValueError, "屏幕内"):
                core._visible_capture_rect(7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
