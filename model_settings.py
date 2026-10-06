"""Provider settings and endpoint-scoped credentials. Secrets never enter config."""
import copy
import hashlib
import queue
import threading
import time
import uuid
from urllib.parse import urlsplit, urlunsplit
import tkinter as tk
from tkinter import ttk

import credential_store as credentials
from ui_theme import BG, WHITE, INK, MUTED, GREEN, RED, FONT, SMALL, make_label, make_button


CUSTOM = "自定义 / 中转平台"
PROVIDERS = {
    CUSTOM: {"base": "", "help": "粘贴供应商文档中的 Base URL，填入完整模型 ID；目前支持 OpenAI 兼容的 Chat Completions 接口。"},
    "OpenAI 官方": {"base": "https://api.openai.com/v1", "help": "使用 OpenAI API 平台的密钥与支持图片输入的模型。ChatGPT 订阅不能代替 API 密钥。"},
    "硅基流动（中国）": {"base": "https://api.siliconflow.cn/v1", "help": "使用硅基流动控制台的 API Key；模型名可能含组织前缀，建议点击获取模型列表。"},
    "阿里云百炼": {"base": "", "help": "请从百炼控制台复制当前业务空间和地域的 OpenAI 兼容 Base URL，选择 Qwen-VL 等支持图片的模型。"},
}


def normalize_base(value):
    value = str(value or "").strip().rstrip("/")
    if value.endswith("/chat/completions"):
        value = value[:-len("/chat/completions")]
    if "{" in value or "}" in value:
        raise ValueError("请填写实际接口地址，替换文档中的工作空间等占位符")
    parsed = urlsplit(value)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or any(ch.isspace() for ch in value):
        raise ValueError("API 地址需要以 https:// 或 http:// 开头，例如供应商给出的 Base URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("API 地址中不能包含密钥、账号密码、查询参数或网页锚点")
    if parsed.path.rstrip("/").endswith(("/messages", "/responses", "/models")):
        raise ValueError("请填写 Chat Completions 的基础地址；目前不支持原生 Messages 或 Responses 接口")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))


def connection_for(cfg, base):
    connections = cfg.get("api_connections") or {}
    saved = connections.get(base) if isinstance(connections, dict) else None
    try:
        same = normalize_base(cfg.get("api_base")) == base
    except ValueError:
        same = False
    if same:
        return {"model": cfg.get("model", ""), "credential_target": cfg.get("api_credential_target", ""),
                "fallback_models": cfg.get("fallback_models", []),
                "send_reasoning_effort": cfg.get("send_reasoning_effort", base != "https://api.openai.com/v1"),
                "token_limit_field": cfg.get("token_limit_field", "max_tokens"),
                "stream_responses": cfg.get("stream_responses", True)}
    return saved if isinstance(saved, dict) else {}


def resolve_key(cfg, base, entered="", current_key=""):
    if entered.strip():
        return entered.strip()
    try:
        same = normalize_base(cfg.get("api_base")) == base
    except ValueError:
        same = False
    if same and current_key:
        return current_key
    connection = connection_for(cfg, base)
    target = connection.get("credential_target", "")
    key = credentials.read_secret(target) if target else ""
    if key:
        return key
    raise ValueError("此接口尚未保存密钥，请填写该供应商的 API Key")


def commit_connection(cfg, base, model, entered, current_key, provider, save_cfg, options=None):
    """Persist first, then update caller state. Never overwrite an active secret."""
    base = normalize_base(base)
    model = model.strip()
    if not model or any(c in model for c in "\r\n"):
        raise ValueError("请填写或选择完整的模型名称")
    key = resolve_key(cfg, base, entered, current_key)
    candidate = copy.deepcopy(cfg)
    connections = copy.deepcopy(candidate.get("api_connections") or {})
    if not isinstance(connections, dict):
        connections = {}
    try:
        old_base = normalize_base(cfg.get("api_base"))
        connections[old_base] = connection_for(cfg, old_base)
    except ValueError:
        pass
    selected = connection_for(cfg, base)
    target = selected.get("credential_target", "")
    new_target = None
    # Rotations use a fresh target so a failed config write cannot break the old app.
    if entered.strip() or not target or credentials.read_secret(target) != key:
        new_target = "WeChatStrategist:ReplyModel:" + hashlib.sha256(base.encode()).hexdigest()[:16] + ":" + uuid.uuid4().hex[:8]
        credentials.write_secret(new_target, key, "桌面搭子模型连接")
        if credentials.read_secret(new_target) != key:
            credentials.delete_secret(new_target)
            raise ValueError("密钥保存后校验失败，请重试")
        target = new_target
    config = {"api_base": base, "model": model, "api_provider": provider,
              "api_credential_target": target, "api_key_source": "credential", "setup_complete": True,
              "fallback_models": list(selected.get("fallback_models") or []),
              "send_reasoning_effort": bool(selected.get("send_reasoning_effort", False)),
              "token_limit_field": selected.get("token_limit_field", "max_completion_tokens" if provider == "OpenAI 官方" else "max_tokens"),
              "stream_responses": bool(selected.get("stream_responses", True))}
    if options:
        config.update(options)
    candidate.update(config)
    connections[base] = {k: config[k] for k in ("model", "fallback_models", "send_reasoning_effort", "token_limit_field", "stream_responses")}
    connections[base]["credential_target"] = target
    candidate["api_connections"] = connections
    try:
        if not save_cfg(candidate):
            raise ValueError("配置保存失败，当前连接保持原样")
    except Exception:
        if new_target:
            credentials.delete_secret(new_target)
        raise
    cfg.clear()
    cfg.update(candidate)
    return key


def fetch_models(base, key):
    import requests
    response = requests.get(normalize_base(base) + "/models", headers={"Authorization": "Bearer " + key}, timeout=(5, 15))
    try:
        response.raise_for_status()
        data = response.json().get("data")
        if not isinstance(data, list):
            raise ValueError("供应商没有返回标准模型列表，请手动填写模型 ID")
        names = sorted({m["id"] for m in data if isinstance(m, dict) and isinstance(m.get("id"), str) and m["id"].strip()})
        if not names:
            raise ValueError("没有获取到模型列表，请手动填写模型 ID")
        return names
    finally:
        response.close()


def test_connection(core, cfg, base, model, key, options=None):
    from PIL import Image
    selected = copy.deepcopy(cfg)
    selected.update(api_base=normalize_base(base), model=model.strip(), fallback_models=[], max_response_tokens=64)
    if not selected["model"]:
        raise ValueError("先填写或选择一个模型，再测试")
    if options:
        selected.update(options)
    text, error = core.call_model(selected, key, core.to_jpeg_b64(Image.new("RGB", (48, 48), "blue")),
                                  "这是程序生成的测试小图。请识别图片颜色，只回复一个颜色名称。",
                                  deadline=time.monotonic()+60)
    if error:
        raise ValueError(error)
    if not ("蓝" in text or "blue" in text.lower()):
        raise ValueError("接口可响应，但测试图未正确识别；请换用支持图片输入的模型")
    return "连接与测试图识别通过。可以保存；实际聊天识别仍需核对。"


class ModelSettings:
    def __init__(self, app):
        self.app, self.core, self.cfg = app, app.core, app.cfg
        self.closed = False
        self.pending = False
        self.job = 0
        self.results = queue.Queue()
        self.top = app.dialog("模型与 API 设置")
        self.top.geometry("650x720")
        self.top.minsize(570, 620)
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self.provider = tk.StringVar(value=self.detect_provider())
        self.base = tk.StringVar(value=self.cfg.get("api_base", ""))
        self.model = tk.StringVar(value=self.cfg.get("model", ""))
        self.secret = tk.StringVar()
        self.reasoning = tk.BooleanVar(value=self.cfg.get("send_reasoning_effort", self.provider.get() != "OpenAI 官方"))
        self.streaming = tk.BooleanVar(value=self.cfg.get("stream_responses", True))
        self.token_field = self.cfg.get("token_limit_field", "max_completion_tokens" if self.provider.get() == "OpenAI 官方" else "max_tokens")
        self.status = tk.StringVar(value="当前连接已填入。模型不变时可直接关闭；密钥框留空表示保留此接口的已存密钥。")
        self.widgets = []
        self.build()
        self.base.trace_add("write", self.base_changed)

    def detect_provider(self):
        base = self.cfg.get("api_base", "").rstrip("/")
        for name, entry in PROVIDERS.items():
            if entry["base"] and base == entry["base"]:
                return name
        return self.cfg.get("api_provider") if self.cfg.get("api_provider") in PROVIDERS else CUSTOM

    def build(self):
        foot = tk.Frame(self.top, bg=BG)
        foot.pack(side="bottom", fill="x", padx=24, pady=(8, 18))
        make_label(foot, "", MUTED, SMALL, textvariable=self.status, wraplength=580).pack(fill="x", pady=(0, 10))
        row = tk.Frame(foot, bg=BG)
        row.pack(fill="x")
        make_button(row, "取消", self.close).pack(side="right")
        self.save_button = make_button(row, "保存并立即生效", self.save, primary=True)
        self.save_button.pack(side="right", padx=(0, 10))

        body = tk.Frame(self.top, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=(18, 0))
        make_label(body, "换一个模型，继续当前聊天", font=(FONT[0], 16, "bold")).pack(anchor="w")
        make_label(body, "选择供应商 → 填密钥 → 选模型 → 测试 → 保存", MUTED, SMALL).pack(anchor="w", pady=(4, 14))
        make_label(body, "API 供应商", font=SMALL).pack(anchor="w")
        provider = ttk.Combobox(body, textvariable=self.provider, values=list(PROVIDERS), state="readonly", font=FONT)
        provider.pack(fill="x", pady=(4, 8))
        provider.bind("<<ComboboxSelected>>", self.provider_changed)
        self.widgets.append(provider)
        self.help = make_label(body, PROVIDERS[self.provider.get()]["help"], MUTED, SMALL, wraplength=580)
        self.help.pack(fill="x", pady=(0, 10))
        self.field(body, "API 基础地址（Base URL）", self.base)
        make_label(body, "完整 /chat/completions 地址也可粘贴，保存时会自动整理。", MUTED, SMALL).pack(anchor="w", pady=(0, 10))
        self.field(body, "API Key（密钥）", self.secret, secret=True)
        make_label(body, "密钥不会回显。换到未保存过的接口时，请填写该供应商的密钥。", MUTED, SMALL, wraplength=580).pack(fill="x", pady=(0, 10))
        make_label(body, "模型名称（必须支持图片输入）", font=SMALL).pack(anchor="w")
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x", pady=(4, 10))
        self.model_combo = ttk.Combobox(row, textvariable=self.model, font=FONT)
        self.model_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.widgets.append(self.model_combo)
        fetch = make_button(row, "获取模型列表", self.get_models, small=True)
        fetch.pack(side="right")
        self.widgets.append(fetch)
        test = make_button(body, "测试连接与识图", self.test, small=True)
        test.pack(anchor="w", pady=(0, 7))
        self.widgets.append(test)
        make_label(body, "测试仅发送程序自带小图，不使用聊天截图；列表中也可能包含不支持图片的模型。", MUTED, SMALL, wraplength=580).pack(fill="x", pady=(0, 8))
        self.advanced = tk.Frame(body, bg=BG)
        make_button(body, "兼容选项 ▾", self.toggle_advanced, small=True).pack(anchor="w")
        for title, variable in (("流式接收响应", self.streaming), ("发送 reasoning_effort 参数（部分接口需要）", self.reasoning)):
            w = tk.Checkbutton(self.advanced, text=title, variable=variable, bg=BG, font=SMALL)
            w.pack(anchor="w")
            self.widgets.append(w)
        self.top.bind("<Escape>", lambda _event: self.close())

    def field(self, body, title, variable, secret=False):
        make_label(body, title, font=SMALL).pack(anchor="w")
        w = tk.Entry(body, textvariable=variable, show="•" if secret else "", font=FONT,
                     bg=WHITE, fg=INK, relief="flat", bd=6)
        w.pack(fill="x", pady=(4, 4))
        self.widgets.append(w)

    def toggle_advanced(self):
        if self.advanced.winfo_ismapped():
            self.advanced.pack_forget()
        else:
            self.advanced.pack(fill="x", pady=(5, 0))
            self.top.geometry("650x800")

    def provider_changed(self, _event=None):
        provider = self.provider.get()
        entry = PROVIDERS[provider]
        self.help.configure(text=entry["help"])
        self.secret.set("")
        self.model_combo.configure(values=[])
        self.base.set(entry["base"])
        connection = connection_for(self.cfg, entry["base"]) if entry["base"] else {}
        self.model.set(connection.get("model", ""))
        self.reasoning.set(connection.get("send_reasoning_effort", False))
        self.streaming.set(connection.get("stream_responses", True))
        self.token_field = connection.get("token_limit_field", "max_completion_tokens" if provider == "OpenAI 官方" else "max_tokens")
        self.status.set("选择能识别图片的模型；新接口需要自己的 API Key。")

    def base_changed(self, *_args):
        self.secret.set("")
        try:
            base = normalize_base(self.base.get())
            connection = connection_for(self.cfg, base)
        except ValueError:
            base, connection = "", {}
        self.reasoning.set(connection.get("send_reasoning_effort", False))
        self.streaming.set(connection.get("stream_responses", True))
        self.token_field = connection.get("token_limit_field", "max_completion_tokens" if base == PROVIDERS["OpenAI 官方"]["base"] else "max_tokens")

    def options(self, base):
        return {"stream_responses": self.streaming.get(), "send_reasoning_effort": self.reasoning.get(),
                "token_limit_field": self.token_field}

    def snapshot(self, require_model=False):
        base = normalize_base(self.base.get())
        model = self.model.get().strip()
        if require_model and not model:
            raise ValueError("先填写或选择一个模型")
        return base, model, resolve_key(self.cfg, base, self.secret.get(), self.app.key), self.options(base)

    def run_async(self, mode, function):
        if self.pending:
            return
        self.pending = True
        self.job += 1
        job = self.job
        self.status.set("正在获取模型列表…" if mode == "models" else "正在测试连接与图片输入…")
        for w in self.widgets + [self.save_button]:
            w.configure(state="disabled")
        def worker():
            try:
                value, error = function(), None
            except Exception as exc:
                value, error = None, self.safe_error(exc)
            self.results.put((job, mode, value, error))
        threading.Thread(target=worker, daemon=True).start()
        self.top.after(100, self.poll)
        self.top.after(65000, lambda: self.expire(job))

    @staticmethod
    def safe_error(exc):
        import requests
        if isinstance(exc, ValueError) and not isinstance(exc, requests.exceptions.JSONDecodeError):
            return str(exc)
        if isinstance(exc, requests.Timeout):
            return "连接或响应超时，可以重试。"
        if isinstance(exc, requests.HTTPError):
            code = exc.response.status_code if exc.response is not None else "未知"
            return "接口返回 HTTP %s：检查密钥权限、模型名称和接口地址；也可手动填模型名。" % code
        if isinstance(exc, requests.RequestException):
            return "网络连接失败，请检查接口地址与网络。"
        return "操作失败（%s），请检查输入后重试。" % type(exc).__name__

    def enable_controls(self):
        for w in self.widgets + [self.save_button]:
            if w.winfo_exists():
                w.configure(state="readonly" if isinstance(w, ttk.Combobox) and w is not self.model_combo else "normal")

    def expire(self, job):
        if not self.closed and self.pending and job == self.job:
            self.job += 1
            self.pending = False
            self.enable_controls()
            self.status.set("测试等待已结束，可以重试。")

    def poll(self):
        if self.closed:
            return
        try:
            job, mode, value, error = self.results.get_nowait()
        except queue.Empty:
            if self.pending:
                self.top.after(100, self.poll)
            return
        if job != self.job:
            if self.pending:
                self.top.after(100, self.poll)
            return
        self.pending = False
        self.enable_controls()
        if error:
            self.status.set(error)
        elif mode == "models":
            self.model_combo.configure(values=value)
            self.status.set("获取到 %d 个模型。请选择支持图片的模型，再测试连接。" % len(value))
            self.model_combo.focus_set()
        else:
            self.status.set(value)

    def get_models(self):
        try:
            base, _, key, _ = self.snapshot()
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.run_async("models", lambda: fetch_models(base, key))

    def test(self):
        try:
            base, model, key, options = self.snapshot(True)
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.run_async("test", lambda: test_connection(self.core, self.cfg, base, model, key, options))

    def save(self):
        if self.pending:
            return
        try:
            base = normalize_base(self.base.get())
            key = commit_connection(self.cfg, base, self.model.get(), self.secret.get(), self.app.key,
                                    self.provider.get(), self.core.save_cfg, self.options(base))
        except Exception as exc:
            self.status.set(self.safe_error(exc))
            return
        self.app.key = key
        self.app.epoch += 1
        self.app.invalidate()
        self.app.refresh_context()
        self.app.set_status("模型连接已更新，立即生效；本次聊天和前情保留。", GREEN)
        self.close()

    def close(self):
        self.closed = True
        self.job += 1
        self.secret.set("")
        self.top.destroy()
