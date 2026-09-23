# -*- coding: utf-8 -*-
"""界面外观的公共部分：配色、圆角卡片、按钮工厂。

从 wx_ui.py 抽出来，是为了让 profile_ui.py 也能用同一套外观，
而不必让两个界面模块互相 import（会成环）。
改这里 = 两个窗口同时变，不会各自漂移。
"""
import tkinter as tk

BG = "#f3f6f4"
WHITE = "#ffffff"
INK = "#192d26"
MUTED = "#718078"
LINE = "#dce5df"
GREEN = "#147d59"
PALE = "#e8f4ed"
RED = "#ad4037"
AMBER = "#e08b00"
FONT = ("Microsoft YaHei UI", 10)
SMALL = ("Microsoft YaHei UI", 9)
TITLE = ("Microsoft YaHei UI", 17, "bold")
HEAD = ("Microsoft YaHei UI", 12, "bold")
BODY = ("Microsoft YaHei UI", 11)


class Panel(tk.Canvas):
    """圆角背景与可自然增长的内容，不固定卡片高度。"""
    def __init__(self, parent, fill=WHITE):
        super().__init__(parent, bg=BG, highlightthickness=0, bd=0, height=40)
        self.fill = fill
        self.body = tk.Frame(self, bg=fill)
        self.window = self.create_window(16, 12, window=self.body, anchor="nw")
        self.bind("<Configure>", self.layout)
        self.body.bind("<Configure>", self.layout)

    def layout(self, _event=None):
        w = max(self.winfo_width(), 60)
        self.itemconfigure(self.window, width=w - 32)
        h = self.body.winfo_reqheight() + 24
        if int(float(self.cget("height"))) != h:
            self.configure(height=h)
        self.delete("surface")
        r = 14
        self.create_polygon(r, 1, w-r, 1, w-1, 1, w-1, r, w-1, h-r,
                            w-1, h-1, w-r, h-1, r, h-1, 1, h-1, 1, h-r,
                            1, r, 1, 1, fill=self.fill, outline=LINE,
                            smooth=True, splinesteps=18, tags="surface")
        self.tag_lower("surface")


def make_button(parent, text, command, primary=False, small=False, danger=False):
    """统一样式的扁平按钮。danger=True 时用红字，用于「删除/不准」这类操作。"""
    if danger:
        bg, fg, hover = PALE, RED, "#f6ded9"
    elif primary:
        bg, fg, hover = GREEN, WHITE, "#116b4d"
    else:
        bg, fg, hover = PALE, GREEN, "#d8ecdf"
    b = tk.Button(parent, text=text, command=command, font=SMALL if small else FONT,
                  bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
                  relief="flat", bd=0, cursor="hand2",
                  padx=10, pady=6 if small else 9, disabledforeground="#98aaa0")
    b.bind("<Enter>", lambda _e: b.configure(bg=hover)
           if str(b.cget("state")) != "disabled" else None)
    b.bind("<Leave>", lambda _e: b.configure(bg=bg))
    return b


def make_label(parent, text, color=INK, font=FONT, **kwargs):
    return tk.Label(parent, text=text, fg=color, bg=parent.cget("bg"),
                    font=font, anchor="w", justify="left", **kwargs)
