# -*- coding: utf-8 -*-
"""First-run setup for packaged builds."""
import json
import queue
import threading
import tkinter as tk
from tkinter import messagebox

import requests

import credential_store as credentials
import jev_advisor as J


def _main_test(api_base, model, key, timeout=40):
    url = api_base.rstrip("/") + "/chat/completions"
    response = requests.post(
        url,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": "只回复 OK"}],
            "max_tokens": 8,
            "temperature": 0,
        },
        timeout=(5, timeout),
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not data.get("choices"):
        raise ValueError("接口返回格式不兼容")
    return True


def _jev_test(endpoint, model, key, timeout=15):
    payload = J.build_payload(
        ["对方：明天下午三点方便开个短会吗？"],
        [{"label": "确认安排", "text": "可以，明天下午三点见。"}],
        model=model,
    )
    response = requests.post(
        endpoint,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Jev 返回格式不兼容")
    return True


class SetupWizard:
    def __init__(self, cfg, save_cfg):
        self.cfg = cfg
        self.save_cfg = save_cfg
        self.saved = False
        self.closed = False
        self.test_results = queue.Queue()
        self.test_pending = False
        self.root = tk.Tk()
        self.root.title("桌面搭子 · 连接设置")
        self.root.geometry("640x680")
        self.root.minsize(560, 600)
        self.root.resizable(True, True)
        self.root.configure(bg="#f5f6f8")
        self.root.protocol("WM_DELETE_WINDOW", self.cancel)
        self.root.bind("<Return>", lambda _event: self.save())
        self.root.bind("<Escape>", lambda _event: self.cancel())

        self.api_base = tk.StringVar(value=cfg.get("api_base", "https://api.openai.com/v1"))
        self.model = tk.StringVar(value=cfg.get("model", "gpt-4o-mini"))
        self.main_key = tk.StringVar()
        self.jev_enabled = tk.BooleanVar(value=bool(cfg.get("jev_enabled", True)))
        self.jev_key = tk.StringVar()
        self.status = tk.StringVar(value="API Key 只会保存到 Windows 凭据管理器。")
        self._build()

    def _label(self, parent, text="", **kwargs):
        kwargs.setdefault("bg", "#f5f6f8")
        kwargs.setdefault("fg", "#20252b")
        return tk.Label(parent, text=text, **kwargs)

    def _entry(self, parent, var, show=None):
        return tk.Entry(parent, textvariable=var, show=show, font=("Microsoft YaHei UI", 10),
                        relief="solid", bd=1, highlightthickness=0)

    def _build(self):
        # Pack the footer first so Windows display scaling can never push the
        # primary action below the visible area.
        footer = tk.Frame(self.root, bg="#f5f6f8")
        footer.pack(side="bottom", fill="x", padx=30, pady=(8, 22))
        self._label(footer, textvariable=self.status, font=("Microsoft YaHei UI", 9),
                    fg="#52606d", wraplength=560, justify="left").pack(anchor="w", pady=(0, 12))
        actions = tk.Frame(footer, bg="#f5f6f8")
        actions.pack(fill="x")
        tk.Button(actions, text="取消", command=self.cancel, width=10).pack(side="right")
        tk.Button(actions, text="保存并开始", command=self.save, width=14,
                  bg="#147d59", fg="white", activebackground="#116849",
                  activeforeground="white").pack(side="right", padx=(0, 10))

        body = tk.Frame(self.root, bg="#f5f6f8")
        body.pack(side="top", fill="both", expand=True, padx=30, pady=(24, 6))
        self._label(body, "欢迎使用桌面搭子", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w")
        self._label(body, "配置一次即可。聊天数据和凭据不会放进程序包。",
                    font=("Microsoft YaHei UI", 10), fg="#66707a").pack(anchor="w", pady=(3, 18))

        self._field(body, "主模型 API 地址", self.api_base)
        self._field(body, "模型名称", self.model)
        self._field(body, "主模型 API Key", self.main_key, secret=True,
                    hint="必填；已保存过时可留空")
        tk.Button(body, text="测试主模型连接", command=self.test_main, cursor="hand2").pack(anchor="w", pady=(0, 14))

        self._label(body, "主模型需要支持图片输入。新版主流程只使用此连接。\n聊天、补充前情和目标会在你操作时提供给主模型。",
                    font=("Microsoft YaHei UI", 9), fg="#66707a", justify="left", wraplength=540).pack(anchor="w", pady=(6, 0))

    def _field(self, parent, title, var, secret=False, hint=""):
        row = tk.Frame(parent, bg="#f5f6f8")
        row.pack(fill="x", pady=(0, 10))
        self._label(row, title, font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w")
        entry = self._entry(row, var, "•" if secret else None)
        entry.pack(fill="x", ipady=6, pady=(3, 0))
        if hint:
            self._label(row, hint, font=("Microsoft YaHei UI", 8), fg="#7b858f").pack(anchor="w", pady=(2, 0))

    def _run_test(self, label, func):
        if self.test_pending:
            return
        self.test_pending = True
        self.status.set(label + "测试中…")

        def worker():
            try:
                func()
                result = (True, label + "连接成功。")
            except requests.ConnectTimeout:
                result = (False, "连接服务超时，请检查接口地址与网络。")
            except requests.ReadTimeout:
                result = (False, "服务已连接，但等待模型返回超时，可稍后重试。")
            except requests.HTTPError as exc:
                result = (False, "接口返回 HTTP %s，请检查模型名称、权限或服务状态。" % exc.response.status_code)
            except Exception as exc:
                result = (False, label + "测试失败（" + type(exc).__name__ + "），请检查连接配置。")
            self.test_results.put(result)

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(100, self._poll_test)

    def _poll_test(self):
        if self.closed:
            return
        try:
            result = self.test_results.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_test)
        else:
            self.test_pending = False
            self.status.set(result[1])

    def test_main(self):
        from model_settings import normalize_base, resolve_key
        try:
            api_base = normalize_base(self.api_base.get())
            key = resolve_key(self.cfg, api_base, self.main_key.get())
        except ValueError as exc:
            self.status.set(str(exc))
            return
        model = self.model.get().strip()
        self._run_test("主模型", lambda: _main_test(api_base, model, key))

    def test_jev(self):
        key = self.jev_key.get().strip() or credentials.read_secret(
            self.cfg.get("jev_credential_target", "WeChatStrategist:Jev"))
        if not key:
            self.status.set("请先填写 Jev API Key；不使用 Jev 也可以直接关闭它。")
            return
        self._run_test("Jev", lambda: _jev_test(
            self.cfg.get("jev_endpoint", J.DEFAULT_ENDPOINT),
            self.cfg.get("jev_model", J.DEFAULT_MODEL), key))

    def save(self):
        from model_settings import commit_connection, normalize_base, connection_for
        api_base = self.api_base.get().strip()
        model = self.model.get().strip()
        main_key = self.main_key.get().strip()
        if not api_base or not model:
            self.status.set("API 地址和模型名称不能为空。")
            return
        try:
            base = normalize_base(api_base)
            provider = "OpenAI 官方" if base == "https://api.openai.com/v1" else "自定义 / 中转平台"
            selected = connection_for(self.cfg, base)
            commit_connection(self.cfg, base, model, main_key, "", provider, self.save_cfg,
                              {"send_reasoning_effort": selected.get("send_reasoning_effort", False),
                               "token_limit_field": selected.get("token_limit_field", "max_completion_tokens" if provider == "OpenAI 官方" else "max_tokens")})
        except Exception as exc:
            self.status.set(str(exc) if isinstance(exc, ValueError) else "保存失败，请检查目录与凭据管理器权限。")
            return
        self.main_key.set("")
        self.jev_key.set("")
        self.saved = True
        self.closed = True
        self.root.destroy()

    def cancel(self):
        self.saved = False
        self.closed = True
        self.root.destroy()

    def run(self):
        self.root.mainloop()
        return self.saved


def run_setup(cfg, save_cfg):
    return SetupWizard(cfg, save_cfg).run()
