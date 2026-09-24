# -*- coding: utf-8 -*-
"""人物画像界面：粘贴聊天 → 生成/更新画像 → 查看与纠正。

单独一个 Toplevel，不碰主窗口的状态（照抄 wx_helper.open_style_editor 的先例）。
网络调用全部在后台线程，事件经自己的 queue + epoch 回主线程，
取消后旧线程的结果会被 epoch 拦掉，不会覆盖新内容。

隐私：profiles/ 里是明文聊天观察 + 逐字原话。这个窗口默认**不显示原话**，
需要手动点「显示原话」。窗口标题里不带联系人名。
"""
import copy
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import profile as P
from ui_theme import (AMBER, BG, BODY, FONT, GREEN, HEAD, INK, LINE, MUTED, PALE,
                      RED, SMALL, TITLE, WHITE, Panel, make_button, make_label)


class ProfileWindow:
    def __init__(self, app):
        self.app = app                      # ReplyApp，用来拿 core/cfg/key/主窗口
        self.core, self.cfg, self.key = app.core, app.cfg, app.key
        self.q = queue.Queue()
        self.epoch = 0
        self.cancel_event = None
        self.busy = False
        self.file_path = None
        self.current = None                 # 当前查看的联系人名
        self.last_deleted = None            # 本窗口中最近一次删除的归档路径
        self.pending_name = ""              # 等用户确认「名字很像，是不是同一个人」
        self.observations = []              # 当前画像的条目（供「不准」按钮定位）
        self.show_quotes = tk.BooleanVar(value=False)
        self.show_evidence = tk.BooleanVar(value=False)
        self.closed = False

        self.top = tk.Toplevel(app.root)
        self.top.title("人物画像 · 本机私密")   # 标题里不放联系人名
        self.top.configure(bg=BG)
        self.top.geometry("680x600")
        self.top.minsize(560, 480)
        self.top.attributes("-topmost", True)
        self.top.protocol("WM_DELETE_WINDOW", self.close)

        self.name_var = tk.StringVar()
        self.status_var = tk.StringVar(value="")
        self.build()
        self.refresh_contacts()
        self.top.after(80, self.pump)

    # ------------------------------------------------------------ 构件
    def button(self, parent, text, command, **kw):
        return make_button(parent, text, command, **kw)

    def label(self, parent, text, color=INK, font=FONT, **kw):
        return make_label(parent, text, color=color, font=font, **kw)

    def build(self):
        head = tk.Frame(self.top, bg=BG)
        head.pack(fill="x", padx=18, pady=(16, 10))
        self.label(head, "人物画像", font=TITLE).pack(side="left")
        self.label(head, "聊天只在本机解析 · 只上传脱敏后的文字",
                   MUTED, SMALL).pack(side="left", padx=(10, 0), pady=(6, 0))

        self.tabs = {}
        tabbar = tk.Frame(self.top, bg=BG)
        tabbar.pack(fill="x", padx=18)
        for key, text in (("import", "导入聊天"), ("view", "查看画像")):
            b = self.button(tabbar, text, lambda k=key: self.switch(k), small=True)
            b.pack(side="left", padx=(0, 6))
            self.tabs[key] = b

        self.pages = tk.Frame(self.top, bg=BG)
        self.pages.pack(fill="both", expand=True, padx=18, pady=(10, 0))
        self.page_import = tk.Frame(self.pages, bg=BG)
        self.page_view = tk.Frame(self.pages, bg=BG)
        self.build_import(self.page_import)
        self.build_view(self.page_view)

        foot = tk.Frame(self.top, bg=BG)
        foot.pack(side="bottom", fill="x", padx=18, pady=(8, 14))
        self.status = self.label(foot, "", MUTED, SMALL, wraplength=600)
        self.status.pack(side="left", fill="x", expand=True)
        self.button(foot, "关闭", self.close).pack(side="right")
        # 不做截图防护：SetWindowDisplayAffinity 挡不住拍屏，而这个工具本身就用
        # PrintWindow 截微信窗口 —— 加上只会挡住自己调试，挡不住任何真实泄露路径。
        # 说清楚局限比给一个假的安全感有用。
        self.label(self.top, "本窗口内容仅存本机；分享屏幕或录屏会把它一起带出去",
                   MUTED, SMALL).pack(side="bottom", fill="x", padx=18, pady=(0, 6))
        self.switch("import")

    def switch(self, key):
        for name, page in (("import", self.page_import), ("view", self.page_view)):
            page.pack_forget()
            self.tabs[name].configure(bg=PALE if name != key else GREEN,
                                      fg=GREEN if name != key else WHITE)
        (self.page_import if key == "import" else self.page_view).pack(fill="both", expand=True)
        self.tab = key
        if key == "view":
            self.refresh_contacts()

    # ------------------------------------------------------------ 导入页
    def build_import(self, page):
        top = Panel(page)
        top.pack(fill="x", pady=(0, 10))
        row = tk.Frame(top.body, bg=WHITE)
        row.pack(fill="x", pady=(0, 8))
        self.label(row, "这是谁？", font=HEAD).pack(side="left")
        self.label(row, "要和微信里显示的名字一致", MUTED, SMALL).pack(side="left", padx=(8, 0))
        self.entry = tk.Entry(top.body, textvariable=self.name_var, font=FONT, bg=BG,
                              fg=INK, insertbackground=GREEN, relief="flat", bd=6)
        self.entry.pack(fill="x", ipady=3)
        hint_row = tk.Frame(top.body, bg=WHITE)
        hint_row.pack(fill="x", pady=(8, 0))
        self.label(hint_row, "已有画像：", MUTED, SMALL).pack(side="left")
        self.known_box = tk.Frame(hint_row, bg=WHITE)
        self.known_box.pack(side="left", fill="x", expand=True)

        paste = Panel(page)
        paste.pack(fill="both", expand=True, pady=(0, 10))
        title = tk.Frame(paste.body, bg=WHITE)
        title.pack(fill="x", pady=(0, 6))
        self.label(title, "粘贴聊天记录 / 导入 Markdown", font=HEAD).pack(side="left")
        self.file_btn = self.button(title, "选择 .md 文件", self.select_md_file, small=True)
        self.file_btn.pack(side="right")
        self.text = tk.Text(paste.body, font=FONT, wrap="word", bg=BG, fg=INK,
                            relief="flat", padx=10, pady=10, height=12,
                            insertbackground=GREEN)
        self.text.pack(fill="both", expand=True)
        self.text.bind("<<Modified>>", self.on_modified)
        self.count_label = self.label(paste.body, "", MUTED, SMALL)
        self.count_label.pack(fill="x", pady=(6, 0))

        actions = tk.Frame(page, bg=BG)
        actions.pack(fill="x")
        self.go = self.button(actions, "生成 / 更新画像", lambda: self.start_extract(), primary=True)
        self.go.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.cancel_btn = self.button(actions, "取消", self.cancel)
        self.cancel_btn.pack(side="left")
        self.cancel_btn.pack_forget()
        self.clear_btn = self.button(actions, "清空", self.clear_text)
        self.clear_btn.pack(side="right")

    def on_modified(self, _event=None):
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        if self.file_path:
            self.file_path = None
        raw = self.text.get("1.0", "end")
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        chars = len(raw)
        self.count_label.configure(text="%d 行 · %d 字" % (len(lines), chars))

    def clear_text(self):
        self.file_path = None
        self.text.delete("1.0", "end")
        self.text.edit_modified(False)
        self.count_label.configure(text="")

    def select_md_file(self):
        path = filedialog.askopenfilename(parent=self.top, title="选择聊天记录 Markdown",
                                          filetypes=[("Markdown 文件", "*.md")])
        if not path:
            return
        if not os.path.isfile(path):
            self.set_status("找不到所选文件，请重新选择", RED)
            return
        self.text.delete("1.0", "end")
        self.text.edit_modified(False)
        self.file_path = path
        self.count_label.configure(text="已选择：%s（%.1f KB）· 点击生成后分段处理" %
                                   (os.path.basename(path), os.path.getsize(path) / 1024))
        self.set_status("文件已选好；请确认上面的联系人名字，再点击生成 / 更新画像", GREEN)

    def prefill(self, name):
        """主窗口已经认出联系人时，直接带过来，省得手输（也就少一次对不上）。"""
        if name and not self.name_var.get().strip():
            self.name_var.set(name)

    def build_known(self, names):
        for child in self.known_box.winfo_children():
            child.destroy()
        if not names:
            self.label(self.known_box, "（还没有）", MUTED, SMALL).pack(side="left")
            return
        for n in names[:6]:
            b = self.button(self.known_box, n, lambda v=n: self.use_known(v), small=True)
            b.pack(side="left", padx=(0, 5))

    def use_known(self, name):
        """点已有画像的名字 = 确认「就是这个人」，把待确认状态清掉。"""
        self.name_var.set(name)
        self.pending_name = ""

    # ------------------------------------------------------------ 画像页
    def build_view(self, page):
        bar = tk.Frame(page, bg=BG)
        bar.pack(fill="x", pady=(0, 8))
        self.label(bar, "选择联系人", MUTED, SMALL).pack(side="left", padx=(0, 8))
        self.picker = tk.Frame(bar, bg=BG)
        self.picker.pack(side="left", fill="x", expand=True)
        self.quote_toggle = tk.Checkbutton(
            bar, text="显示原话", variable=self.show_quotes, command=self.render_profile,
            bg=BG, fg=MUTED, selectcolor=BG, activebackground=BG, font=SMALL, relief="flat")
        self.quote_toggle.pack(side="right")
        self.evidence_toggle = tk.Checkbutton(
            bar, text="显示证据层", variable=self.show_evidence, command=self.render_profile,
            bg=BG, fg=MUTED, selectcolor=BG, activebackground=BG, font=SMALL, relief="flat")
        self.evidence_toggle.pack(side="right", padx=(0, 8))

        scroll = tk.Frame(page, bg=BG)
        scroll.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(scroll, bg=BG, highlightthickness=0, bd=0)
        bar2 = tk.Scrollbar(scroll, orient="vertical", command=self.canvas.yview)
        bar2.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=bar2.set)
        self.body = tk.Frame(self.canvas, bg=BG)
        self.body_id = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>",
                       lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self.body_id, width=e.width))
        self.top.bind("<MouseWheel>", self.mousewheel, add="+")

        tools = tk.Frame(page, bg=BG)
        tools.pack(fill="x", pady=(8, 0))
        self.undo_btn = self.button(tools, "撤销上次画像更新", self.do_undo)
        if P.can_undo(self.current):
            self.undo_btn.pack(side="left")
        else:
            self.undo_btn.pack_forget()
        self.undo_btn.pack_forget()
        self.restore_btn = self.button(tools, "恢复刚删除的画像", self.restore_deleted, small=True)
        self.restore_btn.pack_forget()
        self.delete_btn = self.button(tools, "删除画像…", self.delete_contact,
                                      small=True, danger=True)
        self.delete_btn.pack(side="right", padx=(0, 8))
        self.delete_btn.pack_forget()
        self.merge_btn = self.button(tools, "并入另一个画像…", self.open_merge)
        self.merge_btn.pack(side="right")
        self.merge_btn.pack_forget()

    def mousewheel(self, event):
        if self.closed:
            return
        try:
            if event.widget.winfo_toplevel() == self.top:
                self.canvas.yview_scroll(-int(event.delta / 120), "units")
        except tk.TclError:
            pass

    def refresh_contacts(self):
        names = P.known_contacts()
        self.build_known(names)
        for child in self.picker.winfo_children():
            child.destroy()
        if not names:
            self.label(self.picker, "还没有任何画像 —— 先到「导入聊天」建一个",
                       MUTED, SMALL).pack(side="left")
            self.current = None
            self.render_profile()
            return
        for n in names:
            b = self.button(self.picker, n, lambda v=n: self.select(v), small=True)
            b.pack(side="left", padx=(0, 5))
        if self.current not in names:
            self.current = names[0]
        self.render_profile()

    def select(self, name):
        self.current = name
        self.render_profile()

    def render_profile(self):
        for child in self.body.winfo_children():
            child.destroy()
        self.observations = []
        if not self.current:
            self.undo_btn.pack_forget()
            self.merge_btn.pack_forget()
            self.delete_btn.pack_forget()
            return
        prof = P.load(self.current)
        if not prof:
            self.label(self.body, "读不到「%s」的画像。" % self.current, RED).pack(pady=20)
            return
        obs = prof["observations"]
        portrait = prof.get("portrait") if isinstance(prof.get("portrait"), dict) else None
        self.observations = obs
        s = prof["stats"]
        if P.can_undo(self.current):
            self.undo_btn.pack(side="left")
        else:
            self.undo_btn.pack_forget()
        self.merge_btn.pack(side="right")
        self.delete_btn.pack(side="right", padx=(0, 8))

        info = Panel(self.body)
        info.pack(fill="x", pady=(0, 12))
        self.label(info.body, self.current, font=HEAD).pack(fill="x")
        self.label(info.body,
                   "%d 条证据观察 · 看过 %d 条消息 · 导入 %d 次 · 更新于 %s"
                   % (len(obs), s.get("messages_seen", 0), s.get("batches", 0),
                      (prof.get("updated") or "")[:16].replace("T", " ")),
                   MUTED, SMALL).pack(fill="x", pady=(4, 0))
        if prof.get("migrated"):
            self.label(info.body, "⚠ 有 %d 条旧类别条目已标记「待复核」，不会喂给模型"
                       % prof["migrated"], AMBER, SMALL).pack(fill="x", pady=(4, 0))
        if portrait and portrait.get("stale"):
            self.label(info.body, "⚠ 合并后的整体画像尚未重新归纳；回复暂用证据观察。"
                       "下次导入聊天时会重新生成。", AMBER, SMALL).pack(fill="x", pady=(4, 0))

        if not obs and not portrait:
            self.label(self.body, "这个画像还是空的。", MUTED).pack(pady=16)
            return

        if P.aliases():
            used = {P._safe_name(k): v for k, v in P.aliases().items()}
            mine = [k for k, v in used.items() if P._safe_name(v) == P._safe_name(self.current)]
            if mine:
                self.label(info.body,
                           "识别到的「%s」也算作这个人（不用再确认）" % "」「".join(mine),
                           MUTED, SMALL).pack(fill="x", pady=(4, 0))

        if portrait:
            card = Panel(self.body)
            card.pack(fill="x", pady=(0, 12))
            self.label(card.body, "整体人物画像", font=HEAD).pack(fill="x")
            if portrait.get("overview"):
                self.label(card.body, portrait["overview"], font=BODY,
                           wraplength=550).pack(fill="x", pady=(8, 4))
            for axis in P.PORTRAIT_AXES:
                for trait in portrait.get("traits") or []:
                    if trait.get("axis") != axis:
                        continue
                    self.label(card.body, "%s · %s" % (axis, trait.get("confidence", "低")),
                               GREEN, SMALL).pack(fill="x", pady=(8, 0))
                    self.label(card.body, trait.get("text", ""), font=BODY,
                               wraplength=550).pack(fill="x", pady=(2, 0))
                    self.label(card.body, "%d 条线索支持" % len(trait.get("signal_ids") or []),
                               MUTED, SMALL).pack(fill="x", pady=(2, 0))
                    if self.show_evidence.get():
                        by_id = {s.get("id"): s for s in prof.get("portrait_sources") or []}
                        for sid in (trait.get("signal_ids") or [])[:3]:
                            source = by_id.get(sid)
                            if source:
                                self.label(card.body, "依据：「%s」 %s" %
                                           (source.get("quote", ""), source.get("at", "")),
                                           MUTED, SMALL, wraplength=540).pack(fill="x", pady=(2, 0))
            if portrait.get("reply_tips"):
                self.label(card.body, "回复时的分寸", font=HEAD).pack(fill="x", pady=(12, 2))
                for tip in portrait["reply_tips"]:
                    self.label(card.body, "· " + tip, MUTED, SMALL,
                               wraplength=550).pack(fill="x", pady=(2, 0))

        if not portrait or self.show_evidence.get():
            for kind in P.KINDS:
                group = [o for o in obs if o["kind"] == kind]
                if not group:
                    continue
                head = self.label(self.body, "%s · %d 条" % (kind, len(group)),
                                  GREEN, ("Microsoft YaHei UI", 10, "bold"))
                head.pack(fill="x", padx=4, pady=(8, 6))
                for o in group:
                    self.render_obs(o)

        hint = P.hint(prof)
        hp = Panel(self.body)
        hp.pack(fill="x", pady=(14, 0))
        self.label(hp.body, "回复时的参考卡（实际会动态选取）", font=HEAD).pack(fill="x")
        self.label(hp.body, hint if hint else "（空 —— 现在回复时不会带上任何背景）",
                   MUTED if hint else AMBER, SMALL, wraplength=560).pack(fill="x", pady=(6, 0))

    def render_obs(self, o):
        card = Panel(self.body)
        card.pack(fill="x", pady=(0, 8))
        row = tk.Frame(card.body, bg=WHITE)
        row.pack(fill="x")
        status = o.get("status") or "active"
        marks = {"disputed": " ⚠矛盾", "review": " ⚠待复核"}.get(status, "")
        color = AMBER if status in ("disputed", "review") else INK
        self.label(row, o["text"], color, BODY, wraplength=420).pack(side="left", fill="x", expand=True)
        self.button(row, "不准", lambda i=o["id"]: self.reject_one(i), small=True,
                    danger=True).pack(side="right")
        meta = "%s · %d次 · 最近 %s" % (o["confidence"], o["count"],
                                        (o.get("last_seen") or "未标注"))
        self.label(card.body, meta, MUTED, SMALL).pack(fill="x", pady=(4, 0))
        if self.show_quotes.get():
            for e in o["evidence"]:
                self.label(card.body, "「%s」%s" % (e["quote"], e.get("at") or ""),
                           MUTED, SMALL, wraplength=520).pack(fill="x", pady=(2, 0))
        else:
            self.label(card.body, "原话已隐藏（%d 条）" % len(o["evidence"]),
                       MUTED, SMALL).pack(fill="x", pady=(2, 0))

    def reject_one(self, obs_id):
        if not self.current:
            return
        prof = P.load(self.current)
        if not prof:
            return
        target = next((o for o in prof["observations"] if o["id"] == obs_id), None)
        if not target:
            return
        if not P.reject(self.current, target["text"]):
            self.set_status("未能记住这条拒绝，请检查画像目录", RED)
            return
        P.drop_portrait_quotes(prof, [e.get("quote", "") for e in target.get("evidence") or []])
        P.drop_observation(prof, obs_id)
        if not P.save(prof):
            self.set_status("画像保存失败，请检查画像目录", RED)
            return
        self.render_profile()
        self.set_status("已删除该观察及同原话画像线索；以后不会重新采用它们", GREEN)

    def do_undo(self):
        if not self.current:
            return
        ok = P.undo(self.current)
        self.refresh_contacts()
        self.set_status("已撤销上次画像更新" if ok else "没有可撤销的快照", GREEN if ok else MUTED)

    def delete_contact(self):
        if not self.current or self.busy:
            return
        name = self.current
        confirmed = messagebox.askyesno(
            "删除人物画像", "确定删除「%s」的整份画像吗？\n\n"
            "删除后新生成的回复不再使用它，并移到可恢复归档。"
            "本窗口可点「恢复刚删除的画像」。" % name,
            parent=self.top, icon="warning")
        if not confirmed:
            return
        archive = P.archive_contact(name)
        if not archive:
            self.set_status("删除失败，原画像没有改动", RED)
            return
        self.last_deleted = archive
        self.current = None
        self.refresh_contacts()
        self.restore_btn.pack(side="left", padx=(8, 0))
        self.set_status("已移除「%s」的画像；需要时可点「恢复刚删除的画像」" % name, GREEN)

    def restore_deleted(self):
        if not self.last_deleted or self.busy:
            return
        name = P.restore_archived_contact(self.last_deleted)
        if not name:
            self.set_status("恢复失败：可能已有同名画像，归档仍保留", RED)
            return
        self.last_deleted = None
        self.restore_btn.pack_forget()
        self.current = name
        self.refresh_contacts()
        self.set_status("已恢复「%s」的画像" % name, GREEN)

    def open_merge(self):
        """把另一个联系人的画像并进当前这个。

        唯一需要它的场景：OCR 认错名字，用户没在读取时当场确认，于是同一个人
        攒下了两份画像（名字差一个字）。两份都在，谁也不会自动合并 ——
        difflib 分不开「同一个人」和「不同的人」（实测都是 0.80），
        只能由用户指认。
        """
        if not self.current or self.busy:
            return
        others = [n for n in P.known_contacts() if P._safe_name(n) != P._safe_name(self.current)]
        if not others:
            self.set_status("没有别的画像可以并进来", MUTED)
            return
        top = tk.Toplevel(self.top)
        top.title("并入另一个画像")
        top.configure(bg=BG)
        top.geometry("420x320")
        top.transient(self.top)
        top.grab_set()
        self.label(top, "把哪份画像并进「%s」？" % self.current, font=HEAD).pack(padx=18, pady=(16, 4), anchor="w")
        self.label(top, "被并的那份会被改名成 .merged（不再出现在列表里），不会删掉。",
                   MUTED, SMALL, wraplength=380).pack(padx=18, anchor="w")

        # 列出**全部**候选，不截断。这里原来只取 others[:8]，而画像多起来恰恰是
        # 这条路径要解决的场景（OCR 认错名字，同一个人攒下好几份）——
        # 想并的那份排在第九位之后就不显示，且没有任何提示，用户只会以为它不存在。
        box = tk.Frame(top, bg=BG)
        box.pack(fill="both", expand=True, padx=18, pady=(10, 0))
        lb = tk.Listbox(box, bg=WHITE, fg=INK, font=SMALL, height=6,
                        selectbackground=PALE, selectforeground=INK,
                        highlightthickness=1, highlightbackground=LINE,
                        borderwidth=0, activestyle="none", exportselection=False)
        for n in others:
            lb.insert("end", n)
        lb.selection_set(0)
        lb.see(0)
        sb = tk.Scrollbar(box, command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def go():
            sel = lb.curselection()
            if not sel:                      # 用户把选中取消了：别拿 others[0] 顶包
                return
            src = lb.get(sel[0])
            try:
                moved, _ = P.merge_contact(self.current, src)
            except OSError:
                self.set_status("合并保存失败，源画像仍在", RED)
                return
            top.destroy()
            self.refresh_contacts()
            self.render_profile()
            # 两份画像都可能没有观察条目（用户建了但一条都没过校验），这时 moved=0，
            # 但源画像**确实已经消失了**。只说「没并进任何东西」会让用户以为操作失败，
            # 而列表里那份已经不见了 —— 说清楚发生了什么，别让他去找一份其实并掉了的画像。
            if moved:
                self.set_status("已从「%s」并入 %d 条观察" % (src, moved), GREEN)
            else:
                self.set_status("「%s」是空的，没有观察可并；它已改名成 .merged" % src, MUTED)

        foot = tk.Frame(top, bg=BG)
        foot.pack(side="bottom", fill="x", padx=18, pady=12)
        self.button(foot, "取消", top.destroy).pack(side="right")
        self.button(foot, "并入", go, primary=True).pack(side="right", padx=(0, 8))

    # ------------------------------------------------------------ 后台任务
    def set_busy(self, busy):
        self.busy = busy
        self.go.configure(state="disabled" if busy else "normal")
        self.clear_btn.configure(state="disabled" if busy else "normal")
        self.entry.configure(state="disabled" if busy else "normal")
        self.text.configure(state="disabled" if busy else "normal")
        self.file_btn.configure(state="disabled" if busy else "normal")
        self.delete_btn.configure(state="disabled" if busy else "normal")
        self.restore_btn.configure(state="disabled" if busy else "normal")
        if busy:
            self.cancel_btn.pack(side="left")
        else:
            self.cancel_btn.pack_forget()

    def set_status(self, text, color=MUTED):
        self.status.configure(text=text, fg=color)

    def start_extract(self):
        if self.busy:
            self.set_status("正在处理，可先取消")
            return
        name = self.name_var.get().strip()
        raw = self.text.get("1.0", "end").strip()
        file_path = self.file_path
        if not name:
            self.set_status("先填「这是谁」—— 要和微信里显示的名字一致", RED)
            return
        if not file_path and len([ln for ln in raw.splitlines() if ln.strip()]) < 2:
            self.set_status("粘贴的聊天太短了，至少要有几行带「昵称: 」的消息", RED)
            return

        # 名字对不上时的提示（不自动套用，只问一句）。
        # 只写状态栏是不够的：下一句「正在解析说话人…」会立刻把它盖掉，
        # 用户根本来不及看。所以这里**先不开始**，要求再点一次确认。
        similar = P.similar_contacts(name)
        if similar and P.load(name) is None and self.pending_name != name:
            self.pending_name = name
            self.set_status("已有画像「%s」和「%s」很像。是同一个人就点上面的名字；"
                            "确认是两个人，再点一次「生成 / 更新画像」继续。"
                            % ("」「".join(similar), name), AMBER)
            return
        self.pending_name = ""
        self.epoch += 1
        job = self.epoch
        event = threading.Event()
        self.cancel_event = event
        self.set_busy(True)
        self.set_status("正在解析说话人…", GREEN)
        threading.Thread(target=self.worker, args=(job, event, name, raw, file_path),
                         daemon=True).start()

    def worker(self, job, event, name, raw, file_path=None):
        def emit(kind, value):
            if not event.is_set():
                self.q.put((job, kind, value))
        try:
            cfg = copy.deepcopy(self.cfg)
            checkpoint = None
            base_hash = None
            if file_path:
                with open(file_path, "r", encoding="utf-8-sig") as f:
                    source = f.read()
                chunks, message_count = P.markdown_chat_chunks(source)
                checkpoint = P.import_checkpoint_path(name, source)
                base_hash = P.profile_disk_hash(name)
            else:
                chunks = [raw]
                message_count = len([ln for ln in raw.splitlines() if ln.strip()])
                base_hash = P.profile_disk_hash(name)
            prof = P.load(name) or P.blank(name)
            before = len(prof["observations"])
            stats = {"raw": 0, "kept": 0, "dropped": 0, "scrubbed": 0,
                     "unknown_lines": 0,
                     "drops": {k: 0 for k in ("bad_kind", "too_long", "other_speaker",
                                              "no_quote", "rejected")}}
            added = merged = contra = new_evidence = 0
            signals, fallback_signals = [], []
            start_index = 0
            if checkpoint:
                saved = P.load_import_checkpoint(checkpoint, name, base_hash, len(chunks))
                if saved:
                    prof, stats = saved["profile"], saved["stats"]
                    signals, fallback_signals = saved["signals"], saved["fallback_signals"]
                    added, merged, contra, new_evidence = saved["counts"]
                    before = saved["before"]
                    start_index = saved["next_index"]
                    emit("stage", "已恢复 Markdown 进度：前 %d/%d 段已完成" %
                         (start_index, len(chunks)))

            def extract_parts(chunk, index, depth=0):
                if event.is_set():
                    return []
                try:
                    return [P.extract(self.core, cfg, self.key, chunk, name,
                                      cancel_event=event)]
                except P.FormatRefused:
                    if not file_path:
                        raise
                    return []  # 这段只有「我」或系统消息
                except P.ModelOutputError as exc:
                    if not file_path:
                        raise
                    lines = chunk.splitlines()  # Markdown 转换后一行就是一条完整消息
                    if len(lines) < 2 or depth >= 8:
                        raise ValueError("第 %d/%d 段多次缩小后模型仍未返回有效 JSON；"
                                         "画像未保存。请稍后重试或换一个模型。" %
                                         (index, len(chunks))) from exc
                    middle = len(lines) // 2
                    emit("stage", "第 %d/%d 段输出格式异常，正在拆小重试…" %
                         (index, len(chunks)))
                    return (extract_parts("\n".join(lines[:middle]), index, depth + 1)
                            + extract_parts("\n".join(lines[middle:]), index, depth + 1))

            for index, chunk in enumerate(chunks[start_index:], start_index + 1):
                if event.is_set():
                    return
                if file_path:
                    emit("stage", "正在分析 Markdown：第 %d/%d 段（共 %d 条消息）…" %
                         (index, len(chunks), message_count))
                for obs, part in extract_parts(chunk, index):
                    if event.is_set():
                        return
                    for k in ("raw", "kept", "dropped", "scrubbed", "unknown_lines"):
                        stats[k] += part[k]
                    for k, v in part["drops"].items():
                        stats["drops"][k] += v
                    signals.extend(part.get("signals") or [])
                    fallback_signals.extend(P.signals_from_observations(obs))
                    if not obs:
                        continue
                    emit("stage", "正在合并画像：第 %d/%d 段…" % (index, len(chunks)))
                    a, m, c, e = P.merge_with_evidence(
                        self.core, cfg, self.key, prof, obs, cancel_event=event)
                    added += a
                    merged += m
                    contra += c
                    new_evidence += e
                if event.is_set():
                    return
                if checkpoint:
                    P.save_import_checkpoint(checkpoint, {
                        "contact_key": P.core.contact_key(name),
                        "base_hash": base_hash, "total": len(chunks),
                        "next_index": index, "before": before, "profile": prof,
                        "stats": stats, "signals": signals,
                        "fallback_signals": fallback_signals,
                        "counts": [added, merged, contra, new_evidence]})
            if event.is_set():
                return
            if not stats["kept"] and not signals:
                if checkpoint and os.path.exists(checkpoint):
                    os.unlink(checkpoint)  # 没有可续跑的分析结果，下次应重新提取
                emit("error", "聊天记录已分析完，但没有提取到有依据的画像线索；没有修改画像")
                return
            new_signals = P.add_portrait_signals(prof, signals or fallback_signals)
            if prof["portrait_sources"]:
                emit("stage", "正在归纳整体人物画像…")
                portrait = P.synthesize_portrait(
                    self.core, cfg, self.key, prof["portrait_sources"],
                    cancel_event=event, progress=lambda msg: emit("stage", msg))
                if event.is_set():
                    return
                prof["portrait"] = portrait
            prof["stats"]["batches"] = prof["stats"].get("batches", 0) + 1
            prof["stats"]["messages_seen"] = (prof["stats"].get("messages_seen", 0)
                                              + message_count)
            prof["stats"]["rejected"] = prof["stats"].get("rejected", 0) + stats["dropped"]
            with P.PROFILE_WRITE_LOCK:
                if P.profile_disk_hash(name) != base_hash:
                    emit("error", "处理期间这份画像已被更新；为避免覆盖新内容，本次没有保存，请重新开始")
                    return
                if not P.save(prof, snapshot=True):
                    emit("error", "画像保存失败，请检查目录权限")
                    return
            if checkpoint:
                try:
                    os.unlink(checkpoint)
                except FileNotFoundError:
                    pass
            emit("done", {"name": name, "before": before, "after": len(prof["observations"]),
                          "added": added, "merged": merged, "contra": contra,
                          "new_evidence": new_evidence, "new_signals": new_signals,
                          "portrait_traits": len((prof.get("portrait") or {}).get("traits") or []),
                          "stats": stats})
        except P.FormatRefused as e:
            emit("error", "格式认不出来：%s" % e)
        except (OSError, UnicodeError):
            emit("error", "文件读取失败，请检查文件路径和 UTF-8 编码")
        except ValueError as e:
            emit("error", str(e))
        except Exception as e:
            self.core.log("画像任务失败: %s" % type(e).__name__)
            emit("error", "处理失败，请重试或查看日志")

    def handle_event(self, job, kind, value):
        if job != self.epoch or self.closed:
            return
        if kind == "stage":
            self.set_status(value, GREEN)
            return
        self.set_busy(False)
        if kind == "error":
            self.set_status(value, RED)
            return
        v = value
        s = v["stats"]
        d = s["drops"]
        # 「合并了」和「学到了新东西」是两件事：重复粘贴同一段聊天时模型照样回
        # merge，_absorb 去重后证据不涨。先前这两种情况的文案一模一样，
        # 用户无法判断这段聊天是不是白粘了。
        if v.get("new_evidence", 0) == 0 and v["added"] == 0:
            msg = ("这段聊天没有带来新东西 —— 提取到 %d 条，都和已有条目重复，"
                   "证据一条没增加。（没白跑：说明确实是同一批话）" % s["kept"])
        else:
            msg = ("画像已更新：新增 %d · 合并 %d（新证据 %d 条）· 矛盾 %d。"
                   "提取 %d 条，拦下 %d 条（不是对方说的 %d / 引用搜不到 %d / 超长 %d / 类别非法 %d）"
                   % (v["added"], v["merged"], v.get("new_evidence", 0), v["contra"],
                      s["kept"], s["dropped"],
                      d["other_speaker"], d["no_quote"], d["too_long"], d["bad_kind"]))
        if s["scrubbed"]:
            msg += " · 已屏蔽敏感信息 %d 处" % s["scrubbed"]
        if s["unknown_lines"]:
            msg += " · 有 %d 行没认出说话人，没当证据用" % s["unknown_lines"]
        if v.get("portrait_traits"):
            msg = ("整体画像已更新：%d 个核心特征 · 本次新增 %d 条可核对线索。"
                   % (v["portrait_traits"], v.get("new_signals", 0)))
        self.set_status(msg, GREEN)
        self.clear_text()
        self.current = v["name"]
        self.switch("view")

    def pump(self):
        if self.closed:
            return
        try:
            while True:
                self.handle_event(*self.q.get_nowait())
        except queue.Empty:
            pass
        self.top.after(80, self.pump)

    def cancel(self):
        had_file = bool(self.file_path)
        if self.cancel_event:
            self.cancel_event.set()
        self.epoch += 1
        self.set_busy(False)
        self.set_status("已取消，正式画像没有被改动；再次选择同一文件可接着处理已完成的分段"
                        if had_file else "已取消，画像没有被改动")

    def close(self):
        if self.cancel_event:
            self.cancel_event.set()
        self.closed = True
        self.epoch += 1
        self.top.destroy()
