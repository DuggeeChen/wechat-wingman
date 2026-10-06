#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""启动锁的手动冒烟：真的把密码框弹出来，走一遍「输错 → 输对」「取消」「解锁后启动」。

    python scripts/smoke_lock.py

**CI 不跑这个**（ci.yml 里是逐条点名 test_profile.py / test_ui.py，不是通配），
因为它要开真窗口。test_ui.py 里的 test_startup_lock() 覆盖的是纯逻辑
（密码校验 + testing 旁路），覆盖不到这个对话框本身，所以留这个脚本补上。

会短暂闪一个窗口，全程自动操作，自己关掉。

注意：这里用 button.invoke()，不用 event_generate("<Return>")。
Tk 在 Windows 上收不到合成的键盘事件 —— event_generate("<Return>") 连
when="now" 都不触发绑定（实测），所以合成按键测不出东西。真人敲键盘走的是
真实事件循环，不受这个限制，所以回车提交那条路只能靠手测。
"""
import os
import sys
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import wx_helper as core     # noqa: E402
import wx_ui                 # noqa: E402

CFG = {"personas": {"默认": "口语化"}, "default_persona": "默认", "candidates": 3,
       "contact_personas": {}, "save_debug": False, "lock_password": "3650"}
seen = {}
fails = []


def toplevels(root):
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]


def find(widget, cls, text=None):
    for c in widget.winfo_children():
        if isinstance(c, cls) and (text is None or str(c.cget("text")) == text):
            return c
        got = find(c, cls, text)
        if got is not None:
            return got
    return None


def labels(top):
    out = []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, tk.Label):
                out.append(str(c.cget("text")))
            walk(c)
    walk(top)
    return out


def teardown(app):
    """销毁前先取消挂着的 after，否则 Tk 会为每个残留定时器打一行
    invalid command name "...pump" —— 那是测试自己的噪音，不是程序的问题。"""
    for timer in app.root.tk.call("after", "info"):
        try:
            app.root.after_cancel(timer)
        except tk.TclError:
            pass
    app.root.destroy()


def scenario_wrong_then_right():
    """输错必须留在原地（不退出、不清空密码框以外的东西），输对才放行。"""
    app = wx_ui.ReplyApp(core, CFG, "KEY", testing=True)

    def driver():
        tops = toplevels(app.root)
        if not tops:
            fails.append("没有弹出密码框")
            app.root.quit()
            return
        top = tops[0]
        ent, unlock = find(top, tk.Entry), find(top, tk.Button, "解锁")
        if ent is None or unlock is None:
            fails.append("密码框里缺输入框或解锁按钮")
            top.destroy()
            return
        seen["title"] = top.title()
        seen["masked"] = ent.cget("show") != ""
        seen["topmost"] = bool(top.attributes("-topmost"))

        ent.delete(0, "end")
        ent.insert(0, "9999")
        unlock.invoke()
        app.root.update()
        seen["wrong_hint"] = any("密码不对" in t for t in labels(top))
        seen["still_open"] = bool(toplevels(app.root))
        seen["cleared"] = ent.get() == ""

        ent.delete(0, "end")
        ent.insert(0, "3650")
        unlock.invoke()
        app.root.update()

    app.root.after(150, driver)
    seen["ok"] = app.ask_lock()
    seen["no_window_left"] = not toplevels(app.root)
    teardown(app)


def scenario_cancel():
    """点「退出」= 放弃启动，返回 False。"""
    app = wx_ui.ReplyApp(core, CFG, "KEY", testing=True)

    def driver():
        tops = toplevels(app.root)
        if not tops:
            fails.append("第二次没有弹出密码框")
            app.root.quit()
            return
        quit_btn = find(tops[0], tk.Button, "退出")
        if quit_btn is None:
            fails.append("密码框里没有退出按钮")
            tops[0].destroy()
            return
        quit_btn.invoke()
        app.root.update()

    app.root.after(150, driver)
    seen["cancelled"] = app.ask_lock() is False
    teardown(app)


def scenario_unlocked_app_runs():
    """解锁后主窗口要真的露出来，run() 也不能因为 cancelled 提前返回。"""
    app = wx_ui.ReplyApp(core, CFG, "KEY", testing=True)

    def driver():
        top = toplevels(app.root)[0]
        ent = find(top, tk.Entry)
        ent.delete(0, "end")
        ent.insert(0, "3650")
        find(top, tk.Button, "解锁").invoke()
        app.root.update()
        app.root.after(100, app.root.quit)

    app.root.after(150, driver)
    seen["ok2"] = app.ask_lock()
    app.root.deiconify()
    app.run()                      # 内部会 mainloop，driver 里 quit 掉
    seen["cancelled_flag"] = app.cancelled
    teardown(app)


scenario_wrong_then_right()
scenario_cancel()
scenario_unlocked_app_runs()

for key in ("title", "masked", "topmost", "wrong_hint", "still_open", "cleared",
            "ok", "no_window_left", "cancelled", "ok2", "cancelled_flag"):
    print("%-16s %s" % (key, seen.get(key)))
for f in fails:
    print("FAIL:", f)

good = (not fails
        and seen.get("masked") and seen.get("topmost") and seen.get("wrong_hint")
        and seen.get("still_open") and seen.get("cleared") and seen.get("ok")
        and seen.get("no_window_left") and seen.get("cancelled") is True
        and seen.get("ok2") and seen.get("cancelled_flag") is False)
sys.exit(0 if good else 1)
