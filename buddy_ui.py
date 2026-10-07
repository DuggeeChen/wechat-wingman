"""Desk Buddy 2: evidence first, then reply. Session data stays in memory."""
import copy
import hashlib
import json
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import buddy_context as C
from wx_ui import ReplyApp as LegacyApp
from ui_theme import BG, WHITE, INK, MUTED, GREEN, PALE, RED, AMBER, FONT, SMALL, TITLE, BODY, Panel


class BuddyApp(LegacyApp):
    def build(self):
        self.sessions = []
        self.active = None
        self.pending_capture = None
        self.result = {}
        self.expanded = False
        self.selected_card = 0
        self.requirements_open = False
        self.capture_cache = None
        self.read_restore = None
        self.reply_basis = None
        self.preview_active = False
        self.first_reply_at = None
        self.generation_basis = None
        self.direction_pending = None
        self.direction_history = None
        self.recent_expanded = True
        self.role_controls = []
        self.correction_undo = None
        self.editing_index = None
        self.edit_draft = ""
        self.inline_editor = None
        self.edit_persona = ""
        self.stage = ""
        self.started_at = 0
        self.network_mode = None
        self.draft_dialog = None
        self.draft_output = None
        self.draft_input = self.draft_run = None
        self.boundary = tk.StringVar()
        self.controls = []
        self.dynamic_labels = []
        self.root.title("桌面搭子 · 聊清楚，再回应")
        self.root.minsize(500, 620)

        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=22, pady=(18, 10))
        self.label(head, "桌面搭子", font=TITLE).pack(side="left")
        self.label(head, "  聊清楚，再回应", MUTED, SMALL).pack(side="left", pady=(6, 0))
        self.menu_button = self.button(head, "更多 ···", self.open_menu, small=True)
        self.menu_button.pack(side="right")

        foot = tk.Frame(self.root, bg=BG)
        foot.pack(side="bottom", fill="x", padx=22, pady=(8, 16))
        self.progress = ttk.Progressbar(foot, mode="indeterminate", style="Army.Horizontal.TProgressbar")
        self.status_row = tk.Frame(foot, bg=BG)
        self.status_row.pack(fill="x", pady=(0, 8))
        self.status = self.label(self.status_row, "点击一键读取并生成，也可以先只读取。", MUTED, SMALL, wraplength=350)
        self.status.pack(side="left", fill="x", expand=True)
        self.cancel_button = self.button(self.status_row, "取消", self.cancel, small=True)
        self.retry_button = self.button(self.status_row, "重试", self.retry, small=True)
        actions = tk.Frame(foot, bg=BG)
        actions.pack(fill="x")
        self.quick_button = self.button(actions, "一键读取并生成", lambda: self.start("read_generate"), primary=True)
        self.quick_button.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.go_button = self.button(actions, "只读取", lambda: self.start("read"), small=True)
        self.go_button.pack(side="left", padx=(0, 8))
        self.more_button = self.button(actions, "生成回复", lambda: self.start("generate"), small=True)
        self.more_button.pack(side="left")

        scroll = tk.Frame(self.root, bg=BG)
        scroll.pack(fill="both", expand=True, padx=(20, 8))
        self.canvas = tk.Canvas(scroll, bg=BG, highlightthickness=0)
        bar = ttk.Scrollbar(scroll, orient="vertical", command=self.canvas.yview)
        bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=bar.set)
        self.body = tk.Frame(self.canvas, bg=BG)
        self.body_id = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self.resize_content)
        self.root.bind_all("<MouseWheel>", self.mousewheel, add="+")

        panel = Panel(self.body)
        self.context_panel = panel
        panel.pack(fill="x", pady=(0, 12))
        row = tk.Frame(panel.body, bg=WHITE)
        row.pack(fill="x")
        self.contact_label = self.label(row, "打开一个微信聊天", font=(FONT[0], 13, "bold"))
        self.contact_label.pack(side="left", fill="x", expand=True)
        self.details = self.button(row, "前情 / 纠正", self.show_context, small=True)
        self.details.pack(side="right")
        self.meta = self.label(panel.body, "按需读取 · 本次聊天仅保留在内存", MUTED, SMALL)
        self.meta.pack(fill="x", pady=(5, 10))
        self.recent_box = tk.Frame(panel.body, bg=WHITE)
        self.recent_box.pack(fill="x")
        self.target_row = tk.Frame(panel.body, bg=WHITE)
        self.target_row.pack(fill="x", pady=(8, 0))
        self.target_role_button = self.button(self.target_row, "对方", self.target_role_menu, small=True)
        self.last_message = self.label(self.target_row, "先看清双方消息，再选择要回哪一句。", GREEN, SMALL, wraplength=350)
        self.last_message.pack(side="left", fill="x", expand=True)
        self.last_message.bind("<Configure>", lambda e: self.last_message.configure(wraplength=max(160, e.width)))
        row = tk.Frame(panel.body, bg=WHITE)
        row.pack(fill="x", pady=(8, 0))
        self.recent_toggle = self.button(row, "收起最近消息", self.toggle_recent, small=True)
        self.recent_toggle.pack(side="left")
        self.undo_button = self.button(row, "撤销纠正", self.undo_correction, small=True)
        self.pending_button = self.button(panel.body, "处理待确认的片段", self.resolve_pending, small=True)

        plan = Panel(self.body)
        self.plan_panel = plan
        plan.pack(fill="x", pady=(0, 12))
        row = tk.Frame(plan.body, bg=WHITE)
        row.pack(fill="x")
        self.label(row, "直接生成，按需调整", MUTED, SMALL).pack(side="left")
        self.requirements_button = self.button(row, "特殊要求 ›", self.toggle_requirements, small=True)
        self.requirements_button.pack(side="right")
        self.requirements_box = tk.Frame(plan.body, bg=WHITE)
        self.label(self.requirements_box, "可选：只填写聊天里没有提到的要求。", MUTED, SMALL).pack(anchor="w", pady=(8, 0))
        goal_row = tk.Frame(self.requirements_box, bg=WHITE)
        goal_row.pack(fill="x", pady=(10, 6))
        self.label(goal_row, "想达成", MUTED, SMALL).pack(side="left", padx=(0, 12))
        self.goal_entry = tk.Entry(goal_row, textvariable=self.goal, font=FONT, relief="flat", bg=BG, fg=INK, bd=6)
        self.goal_entry.pack(side="left", fill="x", expand=True)
        boundary_row = tk.Frame(self.requirements_box, bg=WHITE)
        boundary_row.pack(fill="x")
        self.label(boundary_row, "别涉及", MUTED, SMALL).pack(side="left", padx=(0, 12))
        self.boundary_entry = tk.Entry(boundary_row, textvariable=self.boundary, font=FONT, relief="flat", bg=BG, fg=INK, bd=6)
        self.boundary_entry.pack(side="left", fill="x", expand=True)
        self.clear_requirements_button = self.button(self.requirements_box, "清空特殊要求", self.clear_requirements, small=True)
        self.clear_requirements_button.pack(anchor="e", pady=(6, 0))
        row = tk.Frame(plan.body, bg=WHITE)
        row.pack(fill="x", pady=(10, 0))
        self.label(row, "语气", MUTED, SMALL).pack(side="left", padx=(0, 8))
        self.combo = ttk.Combobox(row, textvariable=self.persona, values=list(self.cfg["personas"]), width=10,
                                  state="readonly", font=SMALL, style="Army.TCombobox")
        self.combo.pack(side="left")
        self.combo.bind("<<ComboboxSelected>>", self.persona_changed)
        self.check_button = self.button(row, "检查我写的回复", self.check_draft, small=True)
        self.check_button.pack(side="right")
        self.goal_entry.bind("<KeyRelease>", self.plan_changed)
        self.boundary_entry.bind("<KeyRelease>", self.plan_changed)

        self.advice_box = tk.Frame(self.body, bg=BG)
        self.advice_box.pack(fill="x")
        self.card_box = tk.Frame(self.body, bg=BG)
        self.card_box.pack(fill="x")
        self.refresh_context()
        self.render_cards()
        self.set_busy(False)

    def resize_content(self, event):
        self.canvas.itemconfigure(self.body_id, width=event.width)
        self.last_message.configure(wraplength=max(200, event.width-125))
        self.contact_label.configure(wraplength=max(160, event.width-180))
        self.status.configure(wraplength=max(240, event.width-100))
        for label in self.card_labels + self.dynamic_labels:
            if label.winfo_exists():
                label.configure(wraplength=max(220, event.width-42))

    def set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for w in [self.quick_button, self.go_button, self.details, self.menu_button, self.goal_entry, self.boundary_entry,
                  self.requirements_button, self.clear_requirements_button,
                  self.check_button, self.pending_button, self.recent_toggle, self.target_role_button,
                  self.undo_button] + self.controls + self.role_controls:
            if w.winfo_exists():
                w.configure(state=state)
        self.more_button.configure(state="normal" if self.active and not busy else "disabled")
        self.combo.configure(state="disabled" if busy else "readonly")
        if self.inline_editor is not None and self.inline_editor.winfo_exists():
            self.inline_editor.configure(state=state)
        if busy:
            self.progress.pack(fill="x", pady=(0, 8), before=self.status_row)
            self.progress.start(12)
            self.cancel_button.pack(side="right")
            self.retry_button.pack_forget()
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self.cancel_button.pack_forget()

    def invalidate(self):
        self.direction_pending = None
        self.direction_history = None
        self.preview_active = False
        self.editing_index = None
        self.inline_editor = None
        self.edit_draft = ""
        self.cards = []
        self.reply_basis = None
        self.result = {}
        self.expanded = False
        self.selected_card = 0
        self.render_advice()
        self.render_cards()

    def plan_changed(self, _event=None):
        if self.active:
            new = (self.goal.get().strip(), self.boundary.get().strip())
            if new != (self.active.goal, self.active.boundary):
                if not self.finish_edit():
                    return
                self.active.goal, self.active.boundary = new
                self.active.revision += 1
                self.invalidate()
        self.refresh_requirements()

    def refresh_requirements(self):
        filled = bool(self.goal.get().strip() or self.boundary.get().strip())
        self.requirements_button.configure(text="特殊要求%s %s" % (" · 已设置" if filled else "", "⌄" if self.requirements_open else "›"))

    def toggle_requirements(self):
        if self.busy:
            return
        self.requirements_open = not self.requirements_open
        if self.requirements_open:
            # Pack after the compact controls, without moving the main actions.
            self.requirements_box.pack(fill="x", pady=(6, 0))
        else:
            self.requirements_box.pack_forget()
        self.refresh_requirements()

    def clear_requirements(self):
        if not self.busy:
            self.goal.set("")
            self.boundary.set("")
            self.plan_changed()

    def choose_direction(self, index):
        if self.busy or not 0 <= index < len(self.cards):
            return
        if not self.finish_edit():
            return
        if self.reply_basis is not None and self.reply_basis != self.current_reply_basis():
            self.invalidate()
            self.set_status("聊天上下文已变化，请重新生成。", AMBER)
            return
        self.start("direction", index, self.cards[index]["label"])

    def reply_snapshot(self):
        return {"cards": copy.deepcopy(self.cards), "result": copy.deepcopy(self.result),
                "selected": self.selected_card, "expanded": self.expanded, "basis": self.reply_basis}

    def restore_reply_snapshot(self, saved):
        if saved["basis"] is not None and saved["basis"] != self.current_reply_basis():
            self.invalidate()
            return False
        self.cards, self.result = copy.deepcopy(saved["cards"]), copy.deepcopy(saved["result"])
        self.selected_card, self.expanded = saved["selected"], saved["expanded"]
        self.reply_basis = saved["basis"]
        self.preview_active = False
        self.render_advice()
        self.render_cards()
        return True

    def previous_direction(self):
        if self.busy or not self.direction_history or not self.finish_edit():
            return
        saved, self.direction_history = self.direction_history, None
        if self.restore_reply_snapshot(saved):
            self.set_status("已恢复换写前的建议。", GREEN)

    def merge_direction(self, result):
        request = self.direction_pending
        cards = copy.deepcopy(request["saved"]["cards"])
        cards[request["index"]] = result["cards"][0]
        self.selected_card = request["index"]
        self.result = dict(result, cards=cards)
        self.cards = cards

    def activate(self, conversation):
        self.capture_cache = None
        self.read_restore = None
        self.correction_undo = None
        self.recent_expanded = True
        self.active = conversation
        self.goal.set(conversation.goal)
        self.boundary.set(conversation.boundary)
        self.requirements_open = False
        self.requirements_box.pack_forget()
        self.refresh_requirements()
        chosen = self.core.bound_persona(self.cfg, conversation.name)
        self.persona.set(chosen if chosen in self.cfg["personas"] else self.cfg["default_persona"])
        self.invalidate()
        self.refresh_context()
        self.set_busy(False)

    def refresh_context(self):
        self.role_controls = []
        for w in self.recent_box.winfo_children():
            w.destroy()
        self.pending_button.pack_forget()
        self.target_role_button.pack_forget()
        self.undo_button.pack_forget()
        if not self.active:
            self.context = None
            return
        c = self.active
        self.context = {"name": c.name, "kind": c.kind, "messages": [self.display_message(m) for m in c.messages]}
        self.contact_label.configure(text=c.name + " · " + c.kind)
        omitted = c.payload()["omitted_message_count"]
        info = "已读 %d 条 · %d 处衔接待补 · 关闭后清空" % (len(c.messages), len(c.gaps))
        if omitted:
            info += " · 本次未带入较早 %d 条" % omitted
        self.meta.configure(text=info, wraplength=max(280, self.canvas.winfo_width()-42))
        for m in c.messages[-3:]:
            row = tk.Frame(self.recent_box, bg=WHITE)
            row.pack(fill="x", pady=3)
            role = {"self": "我", "other": m.get("sender") or "对方", "unknown": "待确认"}[m["role"]]
            b = self.button(row, role[:8], lambda: None, small=True)
            b.configure(command=lambda mid=m["id"], anchor=b: self.show_role_menu(mid, anchor))
            self.role_controls.append(b)
            b.pack(side="left", anchor="n", padx=(0, 8))
            if self.busy:
                b.configure(state="disabled")
            label = self.label(row, m["text"][:110] + ("…" if len(m["text"]) > 110 else ""),
                               MUTED if m["role"] == "self" else INK, SMALL,
                               wraplength=max(230, self.canvas.winfo_width()-135), cursor="hand2")
            label.pack(side="left", fill="x", expand=True)
            label.bind("<Configure>", lambda e, w=label: w.configure(wraplength=max(160, e.width)))
            label.bind("<Button-1>", lambda _e, mid=m["id"]: self.select_target(mid))
        target = c.target()
        if target:
            role = {"self": "我", "other": target.get("sender") or "对方", "unknown": "待确认"}[target["role"]]
            self.target_role_button.configure(text=role[:8])
            self.target_role_button.pack(side="left", padx=(0, 8), before=self.last_message)
        self.last_message.configure(text=("继续补充：" if target and target["role"] == "self" else "正在回复：") + target["text"][:120]
                                    if target else "你已回复，等待对方。需要补充时，点击具体消息。",
                                    fg=GREEN if target else MUTED)
        if c.guard() and any(m["role"] == "unknown" for m in c.messages[-6:]):
            self.last_message.configure(text="发送者待确认 · 点消息左侧身份即可纠正", fg=AMBER)
        if c.pending or self.pending_capture:
            self.pending_button.pack(anchor="w", pady=(8, 0))
        self.more_button.configure(text="再给一批" if self.cards else "生成回复")
        self.update_recent_visibility()
        if self.can_undo_correction():
            self.undo_button.pack(side="right")

    def update_recent_visibility(self):
        self.recent_toggle.configure(text=("收起最近消息" if self.recent_expanded else "展开最近 %d 条消息" % min(3, len(self.active.messages) if self.active else 0)))
        if self.recent_expanded:
            self.recent_box.pack(fill="x", before=self.target_row)
        else:
            self.recent_box.pack_forget()

    def toggle_recent(self):
        if not self.busy:
            self.recent_expanded = not self.recent_expanded
            self.update_recent_visibility()

    def target_role_menu(self):
        if self.active and self.active.target():
            self.show_role_menu(self.active.target_id, self.target_role_button)

    def show_role_menu(self, mid, anchor):
        if self.busy or not self.active:
            return
        m = next((m for m in self.active.messages if m["id"] == mid), None)
        if not m:
            return
        c = self.active
        menu = tk.Menu(self.root, tearoff=False)
        self.role_menu = menu
        for label, role in (("是我说的", "self"), ("是对方说的", "other"), ("暂时不确定", "unknown")):
            menu.add_command(label=label, command=lambda r=role, owner=c: self.correct_role(mid, r, owner))
        menu.add_separator()
        menu.add_command(label="编辑原文 / 群聊昵称…", command=lambda: self.edit_message(mid) if self.active is c else None)
        if self.can_undo_correction():
            menu.add_command(label="撤销上次纠正", command=self.undo_correction)
        try:
            menu.tk_popup(anchor.winfo_rootx(), anchor.winfo_rooty()+anchor.winfo_height())
        finally:
            menu.grab_release()

    def remember_correction(self, c, mid, before, target_before):
        after = next(m for m in c.messages if m["id"] == mid)
        self.correction_undo = {"session_id": c.id, "message_id": mid, "before": before,
                                "after": copy.deepcopy(after), "target_before": target_before,
                                "target_after": (c.target_id, c.explicit_target),
                                "message_ids": tuple(m["id"] for m in c.messages)}

    def correct_role(self, mid, role, owner=None):
        if self.busy or not self.active or (owner is not None and self.active is not owner):
            return
        if not self.finish_edit():
            return
        c = self.active
        m = next((m for m in c.messages if m["id"] == mid), None)
        if not m or m["role"] == role:
            return
        before, target = copy.deepcopy(m), (c.target_id, c.explicit_target)
        # Retain the actual group nickname even when toggling the outer identity.
        c.edit(mid, role, m["text"], m.get("sender", ""))
        self.remember_correction(c, mid, before, target)
        self.recent_expanded = True
        self.invalidate()
        self.refresh_context()
        self.set_status("身份已纠正 · 可撤销；重新生成后使用新身份。", GREEN)

    def can_undo_correction(self):
        u = self.correction_undo
        return bool(u and self.active and u["session_id"] == self.active.id and
                    u["message_ids"] == tuple(m["id"] for m in self.active.messages) and
                    any(m == u["after"] for m in self.active.messages if m["id"] == u["message_id"]))

    def undo_correction(self):
        if self.busy or not self.can_undo_correction() or not self.finish_edit():
            return
        c, u = self.active, self.correction_undo
        index = next(i for i, m in enumerate(c.messages) if m["id"] == u["message_id"])
        c.messages[index] = copy.deepcopy(u["before"])
        c.revision += 1
        if (c.target_id, c.explicit_target) == u["target_after"]:
            c.target_id, c.explicit_target = u["target_before"]
        self.correction_undo = None
        self.recent_expanded = True
        self.invalidate()
        self.refresh_context()
        self.set_status("已撤销上次纠正 · 旧建议已清除。", GREEN)

    @staticmethod
    def display_message(m):
        return "%s：%s" % ({"self": "我", "other": m.get("sender") or "对方", "unknown": "待确认"}[m["role"]], m["text"])

    def select_target(self, mid):
        if self.busy or not self.active:
            return
        if not self.finish_edit():
            return
        self.active.target_id = mid
        self.active.explicit_target = True
        self.active.revision += 1
        self.invalidate()
        self.refresh_context()
        self.set_status("已选择回复目标；不会替对方回答你的话。", GREEN)

    def render_advice(self):
        for w in self.advice_box.winfo_children():
            w.destroy()
        if not self.result:
            return
        for key, color in (("situation", MUTED), ("question", AMBER)):
            if self.result.get(key):
                label = self.label(self.advice_box, ("需要确认：" if key == "question" else "") + self.result[key], color,
                                   SMALL, wraplength=max(250, self.canvas.winfo_width()-42))
                label.pack(fill="x", pady=(0, 8))
                self.dynamic_labels = [w for w in self.dynamic_labels if w.winfo_exists()] + [label]
        if self.result.get("question"):
            self.button(self.advice_box, "补充这个背景", self.show_context, small=True).pack(anchor="w", pady=(0, 8))
        if self.result.get("facts"):
            self.button(self.advice_box, "约定与未答问题 · 查看依据", self.show_evidence, small=True).pack(anchor="w", pady=(0, 8))

    def render_cards(self):
        if self.editing_index is not None and self.inline_editor is not None and self.inline_editor.winfo_exists():
            self.edit_draft = self.inline_editor.get("1.0", "end-1c")
        self.inline_editor = None
        for w in self.card_box.winfo_children():
            w.destroy()
        self.card_labels, self.feedback, self.controls = [], {}, []
        self.layout_body()
        if not self.cards:
            self.label(self.card_box, "读取聊天后直接生成回复；需要时再补前情或特殊要求。", MUTED, SMALL,
                       wraplength=400).pack(fill="x", padx=6, pady=16)
            return
        if self.selected_card >= len(self.cards):
            self.selected_card = 0
        if len(self.cards) > 1:
            directions = tk.Frame(self.card_box, bg=BG)
            directions.pack(fill="x", pady=(0, 10))
            self.label(directions, "按方向换写 · 点击生成新回复", MUTED, SMALL).pack(anchor="w", pady=(0, 5))
            for i, card in enumerate(self.cards):
                b = self.button(directions, card["label"], lambda n=i: self.choose_direction(n),
                                primary=i == self.selected_card, small=True)
                b.pack(side="left", padx=(0, 6))
                b.configure(state="disabled" if self.busy else "normal")
                self.controls.append(b)
        order = [self.selected_card] + [i for i in range(len(self.cards)) if i != self.selected_card]
        for i in (order if self.expanded else order[:1]):
            card = self.cards[i]
            panel = Panel(self.card_box)
            panel.pack(fill="x", pady=(0, 10))
            row = tk.Frame(panel.body, bg=WHITE)
            row.pack(fill="x")
            self.label(row, card["label"], GREEN, (FONT[0], 10, "bold")).pack(side="left")
            marker = self.label(row, "", MUTED, SMALL)
            marker.pack(side="right")
            self.feedback[i] = marker
            editing = i == self.editing_index
            for label, func, primary in (("完成" if editing else "编辑", self.finish_edit if editing else lambda n=i: self.show_edit(n), False),
                                          ("复制", lambda n=i: self.copy_card(n), True)):
                b = self.button(row, label, func, primary=primary, small=True)
                b.pack(side="right", padx=(6, 0))
                b.configure(state="disabled" if self.busy and not (self.preview_active and label == "复制") else "normal")
                self.controls.append(b)
            if editing:
                text = tk.Text(panel.body, font=BODY, wrap="word", height=max(3, min(9, len(self.edit_draft)//28+1)),
                               relief="flat", bg=BG, fg=INK, padx=8, pady=8, undo=True)
                text.pack(fill="x", pady=(10, 4))
                text.insert("1.0", self.edit_draft)
                text.configure(state="disabled" if self.busy else "normal")
                self.inline_editor = text
                b = self.button(panel.body, "取消修改", self.cancel_edit, small=True)
                b.pack(anchor="e", pady=(4, 0))
                self.controls.append(b)
            else:
                body = self.label(panel.body, card["text"], font=BODY, wraplength=max(250, self.canvas.winfo_width()-42))
                body.pack(fill="x", pady=(10, 4))
                self.card_labels.append(body)
        if len(self.cards) > 1:
            b = self.button(self.card_box, "收起其他方案" if self.expanded else "查看另外 %d 种回复" % (len(self.cards)-1), self.toggle_cards, small=True)
            b.pack(anchor="w", pady=(0, 8))
            self.controls.append(b)
        if self.direction_history and not self.busy:
            b = self.button(self.card_box, "恢复换写前的建议", self.previous_direction, small=True)
            b.pack(anchor="w", pady=(0, 8))
            self.controls.append(b)

    def layout_body(self):
        order = (self.context_panel, self.card_box, self.advice_box, self.plan_panel) if self.cards else \
                (self.context_panel, self.plan_panel, self.advice_box, self.card_box)
        for widget in order:
            widget.pack_forget()
        for widget in order:
            widget.pack(fill="x", pady=(0, 12) if widget in (self.context_panel, self.plan_panel) else 0)

    def show_edit(self, index):
        if self.busy or not 0 <= index < len(self.cards):
            return
        if self.editing_index == index and self.inline_editor is not None:
            self.inline_editor.focus_set()
            return
        if not self.finish_edit():
            return
        self.editing_index = self.selected_card = index
        self.edit_persona = self.persona.get()
        self.edit_draft = self.cards[index]["text"]
        self.render_cards()
        self.inline_editor.focus_set()
        self.set_status("直接修改卡片 · 完成或复制时保存，取消修改可恢复。", GREEN)

    def finish_edit(self, and_copy=False):
        if self.editing_index is None:
            return True
        if self.busy:
            return False
        index = self.editing_index
        value = self.inline_editor.get("1.0", "end-1c") if self.inline_editor is not None and self.inline_editor.winfo_exists() else self.edit_draft
        value = value.strip()
        if not value or len(value) > 6000:
            self.set_status("请保留回复正文。" if not value else "回复最多 6000 字，请先缩短。", AMBER)
            return False
        self.cards[index]["text"] = value
        self.editing_index = None
        self.edit_draft = ""
        self.inline_editor = None
        self.render_cards()
        self.set_status("修改已保存在当前回复中。", GREEN)
        if and_copy:
            self.copy_card(index)
        return True

    def cancel_edit(self):
        if not self.busy and self.editing_index is not None:
            self.editing_index = None
            self.edit_draft = ""
            self.inline_editor = None
            self.render_cards()
            self.set_status("已取消修改，保留编辑前的回复。", GREEN)

    def mousewheel(self, event):
        if event.widget is not self.inline_editor:
            super().mousewheel(event)

    def toggle_cards(self):
        if (not self.busy or self.preview_active) and self.finish_edit():
            self.expanded = not self.expanded
            self.render_cards()

    def copy_card(self, index):
        if (self.busy and not self.preview_active) or not 0 <= index < len(self.cards):
            return
        if self.reply_basis is not None and self.reply_basis != self.current_reply_basis():
            return
        if not self.finish_edit():
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.cards[index]["text"])
        mark = self.feedback[index]
        mark.configure(text="已复制", fg=GREEN)
        self.root.after(1600, lambda: mark.configure(text="", fg=MUTED) if mark.winfo_exists() else None)

    def edit_message(self, mid):
        if self.busy or not self.active:
            return
        if not self.finish_edit():
            return
        c = self.active
        m = next(m for m in c.messages if m["id"] == mid)
        top = self.dialog("纠正这条消息")
        role = tk.StringVar(value={"self": "我", "other": "对方", "unknown": "待确认"}[m["role"]])
        sender = tk.StringVar(value=m.get("sender", ""))
        row = tk.Frame(top, bg=BG)
        row.pack(fill="x", padx=16, pady=12)
        ttk.Combobox(row, textvariable=role, values=["我", "对方", "待确认"], state="readonly", width=10).pack(side="left")
        self.label(row, "  群聊昵称（可选）", MUTED, SMALL).pack(side="left")
        tk.Entry(row, textvariable=sender, width=15).pack(side="left")
        foot = tk.Frame(top, bg=BG)
        foot.pack(side="bottom", fill="x", padx=16, pady=12)
        text = tk.Text(top, font=FONT, wrap="word", relief="flat", padx=12, pady=12)
        text.pack(fill="both", expand=True, padx=16)
        text.insert("1.0", m["text"])
        def save():
            before, target = copy.deepcopy(m), (c.target_id, c.explicit_target)
            try:
                c.edit(mid, {"我": "self", "对方": "other", "待确认": "unknown"}[role.get()], text.get("1.0", "end"), sender.get())
            except ValueError as exc:
                messagebox.showinfo("请补充", str(exc), parent=top)
                return
            self.remember_correction(c, mid, before, target)
            self.recent_expanded = True
            top.destroy()
            self.invalidate()
            self.refresh_context()
            self.set_status("已纠正身份和正文，旧建议已清除。", GREEN)
        self.button(foot, "保存纠正", save, primary=True).pack(side="right")

    def show_context(self):
        if self.busy or not self.finish_edit():
            return
        if not self.active:
            self.new_manual()
            return
        c = self.active
        top = self.dialog("本次聊天背景 · " + c.name)
        top.geometry("640x660")
        foot = tk.Frame(top, bg=BG)
        foot.pack(side="bottom", fill="x", padx=16, pady=12)
        tabs = ttk.Notebook(top)
        tabs.pack(fill="both", expand=True, padx=16, pady=14)
        bg = tk.Frame(tabs, bg=BG)
        records = tk.Frame(tabs, bg=BG)
        paste = tk.Frame(tabs, bg=BG)
        tabs.add(bg, text="补充前情")
        tabs.add(records, text="全部消息 / 目标")
        tabs.add(paste, text="补充聊天记录")
        self.label(bg, "说明起因、进展、线下发生的事。它会与原话分开提供给模型。", MUTED, SMALL, wraplength=560).pack(fill="x", pady=10)
        background = tk.Text(bg, font=FONT, wrap="word", relief="flat", padx=12, pady=12)
        background.pack(fill="both", expand=True)
        background.insert("1.0", c.background)
        self.label(bg, "仅保留在本次运行内存；生成 / 检查时会发送给已配置的主模型。", MUTED, SMALL, wraplength=560).pack(fill="x", pady=8)

        listing = tk.Listbox(records, font=SMALL, activestyle="none", relief="flat", exportselection=False)
        listing.pack(fill="both", expand=True, pady=10)
        for i, m in enumerate(c.messages):
            listing.insert("end", "%d  %s%s" % (i+1, self.display_message(m)[:100], " [已纠正]" if m.get("corrected") else ""))
        row = tk.Frame(records, bg=BG)
        row.pack(fill="x", pady=8)
        def selected(action):
            indexes = listing.curselection()
            if indexes:
                mid = c.messages[indexes[0]]["id"]
                if not save_background():
                    return
                top.destroy()
                action(mid)
        self.button(row, "纠正身份 / 原文", lambda: selected(self.edit_message), small=True).pack(side="left")
        self.button(row, "回复这条 / 继续补充", lambda: selected(self.select_target), small=True).pack(side="right")

        self.label(paste, "每条一行：我：… / 对方：… / 群成员昵称：…\n无身份标记的文字会保留为待确认。", MUTED, SMALL).pack(fill="x", pady=10)
        pasted = tk.Text(paste, font=FONT, wrap="word", relief="flat", padx=12, pady=12)
        pasted.pack(fill="both", expand=True)
        direction = tk.StringVar(value="补充更早的消息")
        ttk.Combobox(paste, textvariable=direction, values=["补充更早的消息", "追加较新的消息"], state="readonly").pack(anchor="w", pady=8)
        def save_background():
            value = background.get("1.0", "end").strip()
            if len(value) > 6000:
                messagebox.showinfo("前情过长", "背景最多 6000 字，请精简后保存。", parent=top)
                return False
            if value != c.background:
                c.background = value
                c.revision += 1
                self.invalidate()
            return True
        def add_paste():
            try:
                messages = C.pasted_messages(pasted.get("1.0", "end"))
            except ValueError as exc:
                messagebox.showinfo("请检查格式", str(exc), parent=top)
                return
            if not save_background():
                return
            if c.pending:
                messagebox.showinfo("先处理片段", "还有一个补读片段待确认，请先处理。", parent=top)
                return
            outcome = c.ingest(messages, older=direction.get() == "补充更早的消息")
            top.destroy()
            self.invalidate()
            self.refresh_context()
            if outcome == "pending":
                self.resolve_pending()
        self.button(paste, "加入本次聊天", add_paste, small=True).pack(anchor="e", pady=8)
        def read_older():
            if save_background():
                top.destroy()
                self.start("older")
        def save():
            if save_background():
                top.destroy()
                self.refresh_context()
                self.set_status("前情已保存；可以重新生成建议。", GREEN)
        self.button(foot, "微信向上滚动后，补读一屏", read_older, small=True).pack(side="left")
        self.button(foot, "保存前情", save, primary=True).pack(side="right")

    def new_manual(self):
        top = self.dialog("新建独立聊天")
        self.label(top, "联系人 / 会话名称（同名也会新建独立会话）", MUTED, SMALL).pack(anchor="w", padx=20, pady=(20, 8))
        name = tk.StringVar()
        tk.Entry(top, textvariable=name, font=FONT).pack(fill="x", padx=20)
        kind = tk.StringVar(value="单聊")
        ttk.Combobox(top, textvariable=kind, values=["单聊", "群聊"], state="readonly").pack(anchor="w", padx=20, pady=12)
        def create():
            if name.get().strip():
                c = C.Conversation(name.get().strip(), kind.get())
                self.sessions.append(c)
                self.activate(c)
                top.destroy()
                self.show_context()
        self.button(top, "创建并补充前情", create, primary=True).pack(anchor="e", padx=20, pady=20)

    def accept_capture(self, capture, older=False, cache_key=None):
        self.correction_undo = None
        self.recent_expanded = True
        self.capture_cache = None
        c = self.active
        if c and (c.name != capture["name"] or c.kind != capture["kind"]):
            self.pending_capture = (capture, older)
            self.invalidate()
            self.refresh_context()
            self.resolve_pending()
            return "pending"
        if not c:
            c = C.Conversation(capture["name"], capture["kind"])
            # Preserve a goal entered before the very first read.
            c.goal, c.boundary = self.goal.get().strip(), self.boundary.get().strip()
            self.sessions.append(c)
            self.activate(c)
        result = c.ingest(capture["messages"], older=older)
        if cache_key is not None and result in ("merged", "same"):
            # Only the last accepted frame, scoped to this in-memory session.
            self.capture_cache = {"key": cache_key, "session_id": c.id}
        self.invalidate()
        self.refresh_context()
        self.set_busy(False)
        self.set_status("消息已保存，核对身份与回复目标后生成。", GREEN)
        if result == "pending":
            self.resolve_pending()
        return result

    def resolve_pending(self):
        if self.busy:
            return
        if self.pending_capture:
            capture, older = self.pending_capture
            top = self.dialog("检测到不同的聊天对象")
            self.label(top, "当前：%s\n新读取：%s\n请选择归属，避免把不同人的聊天混在一起。" % (self.active.name, capture["name"]),
                       font=FONT, wraplength=460).pack(fill="x", padx=20, pady=20)
            def create():
                c = C.Conversation(capture["name"], capture["kind"])
                c.ingest(capture["messages"])
                self.sessions.append(c)
                self.pending_capture = None
                top.destroy()
                self.activate(c)
            self.button(top, "建立独立会话", create, primary=True).pack(anchor="w", padx=20, pady=8)
            matches = [s for s in self.sessions if s.name == capture["name"] and s.kind == capture["kind"]]
            for index, existing in enumerate(matches):
                def resume(c=existing):
                    self.pending_capture = None
                    top.destroy()
                    self.activate(c)
                    self.accept_capture(capture, older)
                self.button(top, "接回已读会话 %d（%d 条）" % (index+1, len(existing.messages)), resume, small=True).pack(anchor="w", padx=20, pady=5)
            def discard():
                self.pending_capture = None
                top.destroy()
                self.refresh_context()
            self.button(top, "舍弃这次读取", discard, small=True).pack(anchor="w", padx=20, pady=8)
            return
        c = self.active
        if not c or not c.pending:
            return
        top = self.dialog("确认补读片段的顺序")
        pending = c.pending
        self.label(top, "没有找到足够可靠的重叠消息。\n请核对是否同一会话，再确认顺序；衔接缺口会保留标记。", MUTED, SMALL, wraplength=460).pack(fill="x", padx=20, pady=16)
        preview = tk.Text(top, font=SMALL, height=8, wrap="word", relief="flat")
        preview.pack(fill="both", expand=True, padx=20)
        preview.insert("1.0", "\n".join(self.display_message(m) for m in pending["messages"]))
        preview.configure(state="disabled")
        row = tk.Frame(top, bg=BG)
        row.pack(fill="x", padx=20, pady=14)
        def join(older):
            c.ingest(pending["messages"], older=older, force=True)
            top.destroy()
            self.invalidate()
            self.refresh_context()
            self.set_status("片段已连接，衔接处标记为可能缺消息。", AMBER)
        def discard():
            c.pending = None
            top.destroy()
            self.refresh_context()
        self.button(row, "放到更早", lambda: join(True), small=True).pack(side="left", padx=(0, 8))
        self.button(row, "接在后面", lambda: join(False), small=True).pack(side="left")
        self.button(row, "舍弃片段", discard, small=True).pack(side="right")

    def start(self, mode, index=None, instruction=""):
        if self.busy or self.root.grab_current() is not None:
            self.set_status("请先完成编辑或取消当前任务。", AMBER)
            return
        if not self.finish_edit():
            return
        if self.pending_capture or (self.active and self.active.pending):
            self.resolve_pending()
            return
        self.plan_changed()
        is_read = mode in ("read", "older", "read_generate")
        if not is_read:
            problem = self.active.guard() if self.active else "请先读取聊天"
            if mode == "check" and self.active and self.active.messages and not any(m["role"] == "unknown" for m in self.active.messages[-6:]):
                problem = ""
            if problem:
                self.set_status(problem, AMBER)
                return
        if mode == "direction" and (index is None or not 0 <= index < len(self.cards)):
            self.set_status("请先生成回复，再选择方向。", AMBER)
            return
        self.epoch += 1
        job = self.epoch
        event = threading.Event()
        self.cancel_event = event
        self.last_retry = (mode, index, instruction)
        self.network_mode = mode
        self.started_at = time.monotonic()
        self.first_reply_at = None
        self.generation_basis = self.current_reply_basis() if mode in ("generate", "direction") else None
        self.stage = ("正在按「%s」换写" % instruction if mode == "direction" else
                      "正在识别聊天" if is_read else "正在检查草稿" if mode == "check" else "正在生成回复")
        self.set_busy(True)
        payload = {"cfg": copy.deepcopy(self.cfg), "conversation": copy.deepcopy(self.active),
                   "style": self.cfg["personas"].get(self.persona.get(), "自然简短"),
                   "previous": [c["text"] for c in self.cards], "draft": instruction,
                   "direction": instruction if mode == "direction" else None,
                   "cache": copy.deepcopy(self.capture_cache), "session_id": self.active.id if self.active else None,
                   "basis": self.current_reply_basis()}
        self.read_restore = self.reply_snapshot() if is_read else None
        if mode == "direction":
            if self.direction_history:
                payload["previous"] += [c["text"] for c in self.direction_history["cards"]]
            self.direction_pending = {"index": index, "label": instruction, "saved": self.reply_snapshot()}
            self.selected_card = index
            self.preview_active = False
            self.render_cards()
        # Never display stale candidates during a fresh capture/generation.
        if mode not in ("check", "direction"):
            self.invalidate()
        self.tick(job)
        threading.Thread(target=self.worker, args=(job, event, mode, payload), daemon=True).start()

    def tick(self, job):
        if not self.closed and self.busy and job == self.epoch:
            message = ("完整回复已可复制 · 正在补齐其他建议" if self.preview_active else self.stage)
            self.set_status("%s · 已等待 %d 秒" % (message, time.monotonic()-self.started_at), GREEN)
            self.root.after(1000, lambda: self.tick(job))

    def worker(self, job, event, mode, payload):
        def emit(kind, value):
            if not event.is_set():
                self.q.put((job, kind, value))
        stage = "capture" if mode in ("read", "older", "read_generate") else "check" if mode == "check" else "generate"
        stage_name = {"capture": "识别", "generate": "生成", "check": "检查"}[stage]
        stage_started = time.monotonic()
        outcome = "失败"
        try:
            cfg = payload["cfg"]
            image = None
            if mode in ("read", "older", "read_generate"):
                status, hwnd = self.core.find_wechat()
                if status != "ok":
                    raise ValueError("请打开具体微信聊天，并恢复最小化的窗口")
                image = self.core.grab(hwnd)
                if image is None:
                    raise ValueError("截图失败，请恢复微信窗口后重试")
                cache_key = self.capture_key(image, hwnd, cfg, mode == "older")
                cache = payload.get("cache")
                if cache and cache["session_id"] == payload.get("session_id") and cache["key"] == cache_key:
                    outcome = "缓存命中"
                    emit("reused", cache["session_id"])
                    return
                image = self.core.to_jpeg_b64(self.core.crop_chat(image, cfg))
                prompt = C.CAPTURE_PROMPT
            else:
                prompt = C.generation_prompt(payload["conversation"], payload["style"], payload["previous"],
                                             payload["draft"] if mode == "check" else None,
                                             direction=payload.get("direction"))
            if event.is_set():
                return
            prepared_at = time.monotonic()
            collector = None
            last_preview = None
            def progress(part):
                nonlocal collector, last_preview
                if event.is_set():
                    return
                if part is None:
                    collector = C.GenerationStream(payload["conversation"])
                    last_preview = None
                    emit("preview_reset", payload["basis"])
                else:
                    for result in collector.feed(part):
                        if mode == "direction":
                            try:
                                result = C.direction_result(result, payload["direction"], payload["previous"])
                            except ValueError:
                                continue
                        last_preview = result
                        emit("partial", (result, payload["basis"]))
            text, error = self.core.call_model(cfg, self.key, image, prompt, cancel_event=event,
                                               deadline=time.monotonic()+60, stage=stage,
                                               on_delta=progress if stage == "generate" else None)
            received_at = time.monotonic()
            if event.is_set():
                outcome = "取消"
                return
            if error:
                raise ValueError(error)
            if mode in ("read", "older", "read_generate"):
                emit("capture", (C.parse_capture(text), mode == "older", cache_key))
            elif mode == "check":
                emit("checked", C.unpack_json(text))
            else:
                result = C.parse_generation(text, payload["conversation"])
                if mode == "direction":
                    result = C.direction_result(result, payload["direction"], payload["previous"])
                if last_preview and (result["cards"][:len(last_preview["cards"])] != last_preview["cards"] or
                                     result["question"] != last_preview["question"]):
                    raise ValueError("生成结果前后不一致，请重试；已读消息保留")
                emit("generated", result)
            outcome = "完成"
            self.core.log("流程阶段=%s prepare=%.2fs api=%.2fs parse=%.2fs" %
                          (stage_name, prepared_at-stage_started, received_at-prepared_at, time.monotonic()-received_at))
        except Exception as exc:
            self.core.log("v2 %s failed: %s" % (mode, type(exc).__name__))
            emit("error", str(exc) if isinstance(exc, ValueError) else "处理失败，请重试；已读消息仍保留")
        finally:
            self.core.log("流程阶段=%s total=%.2fs outcome=%s" %
                          (stage_name, time.monotonic()-stage_started, "取消" if event.is_set() else outcome))

    @staticmethod
    def capture_key(image, hwnd, cfg, older=False):
        # Exact pixels of the full window include the contact title and selection.
        # No approximate matching: changes of even one pixel trigger recognition.
        settings = {k: cfg.get(k) for k in ("api_base", "model", "fallback_models", "api_credential_target",
                    "capture_sidebar_max_px", "stream_responses", "send_reasoning_effort",
                    "token_limit_field", "max_response_tokens")}
        return (hwnd, image.mode, image.size, hashlib.sha256(image.tobytes()).digest(), older,
                json.dumps(settings, sort_keys=True, ensure_ascii=False))

    def continue_read(self, job):
        if self.closed or job != self.epoch or self.busy or self.pending_capture or not self.active:
            return
        problem = self.active.guard()
        if problem:
            self.set_status("已读取 · " + problem, AMBER)
            return
        if self.root.grab_current() is not None:
            return
        if self.cards and self.reply_basis == self.current_reply_basis():
            self.set_status("画面未变化 · 沿用当前回复，需要新方案可点「再给一批」。", GREEN)
        else:
            self.start("generate")

    def current_reply_basis(self):
        c = self.active
        if not c:
            return None
        connection = {k: self.cfg.get(k) for k in ("api_base", "model", "fallback_models", "api_credential_target",
                      "stream_responses", "send_reasoning_effort", "token_limit_field", "max_response_tokens")}
        return (c.id, c.revision, c.target_id, c.explicit_target, c.background, c.goal, c.boundary,
                self.cfg["personas"].get(self.persona.get(), "自然简短"),
                json.dumps(connection, sort_keys=True, ensure_ascii=False))

    def handle_event(self, job, kind, value):
        if kind == "hotkey":
            self.start("read")
            return
        if self.closed or job != self.epoch:
            return
        if kind in ("partial", "preview_reset"):
            if not self.busy or self.network_mode not in ("generate", "direction"):
                return
            basis = value[1] if kind == "partial" else value
            if basis != self.current_reply_basis():
                return
            if kind == "preview_reset":
                if self.preview_active:
                    if self.network_mode == "direction" and self.direction_pending:
                        self.restore_reply_snapshot(self.direction_pending["saved"])
                        self.selected_card = self.direction_pending["index"]
                        self.render_cards()
                    else:
                        self.invalidate()
                    self.recent_expanded = True
                    self.refresh_context()
                self.set_status(self.stage + " · 等待完整候选。", GREEN)
                return
            result = value[0]
            first = not self.preview_active
            self.preview_active = True
            if self.network_mode == "direction" and self.direction_pending:
                self.merge_direction(result)
            else:
                self.result, self.cards = result, result["cards"]
            self.reply_basis = basis
            self.recent_expanded = False
            self.render_advice()
            self.render_cards()
            self.refresh_context()
            if first:
                elapsed = time.monotonic()-self.started_at
                if self.first_reply_at is None:
                    self.first_reply_at = elapsed
                    self.core.log("阶段=生成 first_usable=%.2fs" % elapsed)
                self.root.after_idle(lambda: self.canvas.yview_moveto(0) if not self.closed and job == self.epoch else None)
            self.set_status("完整回复已可复制 · 正在补齐其他建议。", GREEN)
            return
        if kind == "generated" and self.generation_basis is not None and self.generation_basis != self.current_reply_basis():
            self.handle_event(job, "error", "聊天上下文已变化，请重新生成。")
            return
        had_preview = self.preview_active
        self.set_busy(False)
        if kind == "error":
            self.generation_basis = None
            if self.network_mode == "direction" and self.direction_pending:
                saved = self.direction_pending["saved"]
                self.direction_pending = None
                self.restore_reply_snapshot(saved)
                if had_preview:
                    value = "换写未完成，已恢复原建议；如已复制新内容，请先核对。" + value
            elif had_preview:
                self.invalidate()
                self.refresh_context()
                value = "生成未完成，已撤下本次候选；如已复制，请先核对。" + value
            self.read_restore = None
            self.set_status(value, RED)
            self.retry_button.pack(side="right")
            if self.draft_dialog is not None and self.draft_dialog.winfo_exists():
                self.show_check_output("检查失败：" + value)
            return
        if kind == "capture":
            automatic = self.network_mode == "read_generate"
            self.read_restore = None
            outcome = self.accept_capture(*value)
            if automatic and outcome in ("merged", "same"):
                self.continue_read(job)
        elif kind == "reused":
            if not self.active or value != self.active.id:
                self.read_restore = None
                return
            saved, self.read_restore = self.read_restore, None
            if saved:
                self.cards, self.result = saved["cards"], saved["result"]
                self.selected_card, self.expanded = saved["selected"], saved["expanded"]
                self.reply_basis = saved["basis"]
                if self.reply_basis is not None and self.reply_basis != self.current_reply_basis():
                    self.invalidate()
            self.render_advice()
            self.render_cards()
            self.refresh_context()
            self.set_status("画面未变化 · 沿用已读消息和手动纠正，无需重复识别。", GREEN)
            if self.network_mode == "read_generate":
                self.continue_read(job)
        elif kind == "generated":
            self.generation_basis = None
            self.preview_active = False
            direction = self.network_mode == "direction" and self.direction_pending is not None
            if direction:
                self.merge_direction(value)
                self.direction_history = self.direction_pending["saved"]
                self.direction_pending = None
            else:
                self.result = value
                self.cards = value["cards"]
            self.reply_basis = self.current_reply_basis()
            self.recent_expanded = False
            self.render_advice()
            self.render_cards()
            self.refresh_context()
            self.root.after_idle(lambda: self.canvas.yview_moveto(0) if not self.closed and job == self.epoch else None)
            self.set_status("已按所选方向生成新回复 · 其他方案保留，可恢复上一版。" if direction else
                            "建议已生成 · 请核对后复制；不会自动发送。", GREEN)
        elif kind == "checked":
            lines = [C.clean(value.get("summary"), 500) or "检查完成"]
            issues = value.get("issues")
            if isinstance(issues, list):
                for item in issues[:3]:
                    if isinstance(item, dict):
                        lines.append("• %s\n  %s" % (C.clean(item.get("quote"), 300), C.clean(item.get("reason"), 500)))
            if C.clean(value.get("revision"), 2000):
                lines.append("可选修改：\n" + C.clean(value["revision"], 2000))
            self.show_check_output("\n\n".join(lines))
            self.set_status("检查完成，保留你的原稿，由你决定是否采用。", GREEN)

    def cancel(self):
        direction_saved = self.direction_pending["saved"] if self.direction_pending else None
        self.direction_pending = None
        self.generation_basis = None
        if self.preview_active and direction_saved is None:
            self.invalidate()
            self.recent_expanded = True
        super().cancel()
        if direction_saved:
            self.restore_reply_snapshot(direction_saved)
            self.set_status("换写已取消，原建议已保留。", AMBER)
        self.refresh_context()
        self.read_restore = None
        if self.draft_dialog is not None and self.draft_dialog.winfo_exists():
            self.show_check_output("检查已取消，可以修改后重新检查。")

    def check_draft(self, initial=""):
        if self.busy or not self.active:
            self.set_status("先读取聊天，再检查草稿。", AMBER)
            return
        top = self.dialog("发送前检查 · 保留你的表达")
        self.draft_dialog = top
        top.geometry("630x650")
        self.label(top, "结合已读消息、前情、目标与底线，检查承诺、矛盾和不必要的披露。", MUTED, SMALL, wraplength=570).pack(fill="x", padx=20, pady=12)
        draft = tk.Text(top, height=6, font=FONT, wrap="word", relief="flat", padx=10, pady=10)
        self.draft_input = draft
        draft.pack(fill="x", padx=20)
        draft.insert("1.0", initial)
        row = tk.Frame(top, bg=BG)
        row.pack(fill="x", padx=20, pady=10)
        self.draft_output = tk.Text(top, font=FONT, wrap="word", relief="flat", padx=10, pady=10, state="disabled")
        self.draft_output.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        def run():
            text = draft.get("1.0", "end").strip()
            if not text or self.busy:
                return
            if len(text) > 6000:
                self.show_check_output("草稿最多 6000 字，请精简后检查。")
                return
            top.grab_release()
            self.start("check", instruction=text)
            top.grab_set()
            if self.busy:
                self.show_check_output("正在检查…关闭此窗口即可取消本次检查。")
                draft.configure(state="disabled")
                self.draft_run.configure(state="disabled")
            else:
                self.show_check_output(self.status.cget("text"))
        def close():
            if self.busy and self.network_mode == "check":
                self.cancel()
            self.draft_dialog = self.draft_output = self.draft_input = self.draft_run = None
            top.destroy()
        top.protocol("WM_DELETE_WINDOW", close)
        self.draft_run = self.button(row, "检查这段话", run, primary=True)
        self.draft_run.pack(side="right")

    def show_check_output(self, text):
        if not self.busy:
            for w in (self.draft_input, self.draft_run):
                if w is not None and w.winfo_exists():
                    w.configure(state="normal")
        if self.draft_output is not None and self.draft_output.winfo_exists():
            self.draft_output.configure(state="normal")
            self.draft_output.delete("1.0", "end")
            self.draft_output.insert("1.0", text)
            self.draft_output.configure(state="disabled")

    def show_evidence(self):
        if self.busy or not self.active:
            return
        top = self.dialog("模型归纳的约定与未答问题 · 核对原话")
        body = tk.Text(top, font=FONT, wrap="word", relief="flat", padx=16, pady=16)
        body.pack(fill="both", expand=True)
        by_id = {m["id"]: m for m in self.active.messages}
        for fact in self.result.get("facts", []):
            body.insert("end", fact["text"] + "\n")
            for mid in fact["evidence_ids"]:
                body.insert("end", "  依据：" + self.display_message(by_id[mid]) + "\n")
            body.insert("end", "\n")
        body.configure(state="disabled")

    def persona_changed(self, _event=None):
        if not self.finish_edit():
            self.persona.set(self.edit_persona)
            return
        self.invalidate()
        self.set_status("语气已改变，重新生成后生效。")

    def open_menu(self):
        if not self.finish_edit():
            return
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="模型与 API 设置", command=self.open_model_settings)
        menu.add_separator()
        menu.add_checkbutton(label="窗口置顶", variable=self.topmost, command=self.toggle_topmost)
        menu.add_command(label="新建独立聊天 / 手动导入", command=self.new_manual)
        if self.sessions:
            sub = tk.Menu(menu, tearoff=False)
            for i, c in enumerate(self.sessions):
                sub.add_command(label="%s · 会话 %d · %d 条" % (c.name, i+1, len(c.messages)), command=lambda c=c: self.switch_session(c))
            menu.add_cascade(label="本次已读会话", menu=sub)
        menu.add_separator()
        menu.add_command(label="语气风格库", command=self.open_styles)
        menu.add_command(label="旧版人物画像（手动管理）", command=self.open_profile)
        menu.add_command(label="清空当前聊天记忆", command=self.clear_session)
        menu.add_command(label="清理截图与临时数据", command=self.clear_temporary_data)
        menu.add_separator()
        menu.add_command(label="关于上下文与隐私", command=lambda: messagebox.showinfo("桌面搭子 2", "只在你点击时截图。\n生成或检查时，将本次选中的聊天、前情、目标与底线发给你配置的主模型。\n聊天仅在本次运行内存中保留，关闭后清空。\n主流程不再自动更新人物画像或调用 Jev。\n截图身份仍可能识别错误，请核对。", parent=self.root))
        menu.tk_popup(self.menu_button.winfo_rootx(), self.menu_button.winfo_rooty()+self.menu_button.winfo_height())

    def open_model_settings(self):
        if self.busy:
            self.set_status("请先完成或取消当前任务，再修改模型连接。")
            return
        from model_settings import ModelSettings
        self.model_settings = ModelSettings(self)

    def switch_session(self, c):
        if self.pending_capture:
            self.resolve_pending()
            return
        self.activate(c)

    def clear_session(self):
        if self.active and messagebox.askyesno("清空当前聊天", "清除这次会话的消息、前情、目标与建议？其他会话不受影响。", parent=self.root):
            old = self.active
            c = C.Conversation(old.name, old.kind)
            self.sessions[self.sessions.index(old)] = c
            self.pending_capture = None
            self.activate(c)

    def clear_temporary_data(self):
        if self.busy or self.root.grab_current() is not None:
            self.set_status("请先完成或取消当前任务，再清理临时数据。", AMBER)
            return
        if not self.finish_edit():
            return
        from runtime_cleanup import clean_temporary_data
        result = clean_temporary_data(self.core.DATA_DIR)
        self.capture_cache = None
        self.read_restore = None
        released = "%.1f KB" % (result["bytes"]/1024) if result["bytes"] < 1024*1024 else "%.1f MB" % (result["bytes"]/(1024*1024))
        if result["failed"]:
            self.set_status("已重置识别缓存 · 清理 %d 个文件（约 %s），另有 %d 个文件未能清理。" %
                            (len(result["removed"]), released, len(result["failed"])), AMBER)
        elif result["removed"]:
            self.set_status("已清理 %d 个临时文件（约 %s）并重置识别缓存 · 聊天和 API 设置保留。" %
                            (len(result["removed"]), released), GREEN)
        else:
            self.set_status("识别缓存已重置 · 没有待清理的截图或日志，聊天和 API 设置保留。", GREEN)

    def run(self):
        if not self.cancelled:
            self.core.log("桌面搭子 2 上下文界面已启动")
            self.root.mainloop()
