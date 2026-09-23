#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""界面接线的回归测试。不联网、不调模型、不写真实画像目录、不碰真实 config.json。

    python scripts/test_ui.py

覆盖的是**已经真实翻过车**的那几处：
  · 风格绑定与画像必须用同一套名字归一 —— OCR 多一个尾随空格，
    先前会「有画像但判定成没画像」而静默跳过补发（两套匹配不同源）
  · 「有画像」的判据是背景块非空，不是画像文件存在 —— 否则全过期/全待复核的
    画像会白发一次请求，还会说出「已参考画像」这句空话
  · 画像/换风格是附加收益，它的失败**绝不能**摧毁第一轮已经拿到的候选
  · 第二轮没给出候选时，第一轮的结果必须保住，而不是报「模型没有返回有效候选」
  · 背景块被模型吐回来时不能变成一张卡片
  · 一次读取的两轮请求共享同一个超时预算（否则最坏 45+45=90 秒）
"""
import os
import queue
import shutil
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import profile as P          # noqa: E402
import wx_helper as core     # noqa: E402
import wx_ui                 # noqa: E402

# 画像目录指向临时目录，绝不碰真实的 profiles/
_TMP = tempfile.mkdtemp(prefix="wxui-test-")
P.PROFILE_DIR = os.path.join(_TMP, "profiles")
P.HISTORY_DIR = os.path.join(P.PROFILE_DIR, ".history")
P.REJECTED_PATH = os.path.join(P.PROFILE_DIR, ".rejected.json")
# ALIAS_PATH 也必须重定向：它是个独立的模块常量，不跟着 PROFILE_DIR 走。
# 漏掉它的话，测试里任何一次 set_alias 都会写进**真实的** profiles/.aliases.json ——
# 那是用户本机「谁是谁」的记录，测试不该碰，更不该往里塞假名字。
P.ALIAS_PATH = os.path.join(P.PROFILE_DIR, ".aliases.json")

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s  %s" % (name, detail))
        FAILED.append(name)


def eq(name, got, want):
    check(name, got == want, "got=%r want=%r" % (got, want))


ZW = "​"          # 零宽空格：微信昵称里很常见，str.strip() 去不掉


# ---------------------------------------------------------------- 名字归一
def test_contact_key():
    print("\n[联系人名唯一键]")
    eq("尾随空格被归一", core.contact_key("陈晓明 "), "陈晓明")
    eq("零宽字符被归一", core.contact_key("陈晓明" + ZW), "陈晓明")
    eq("内部空格被归一", core.contact_key("6 6"), "66")
    eq("与画像文件名同源", core.contact_key("苏晚 @云图设计"), P._safe_name("苏晚 @云图设计"))
    eq("空名安全", core.contact_key(None), "")
    check("两套实现确实同源（画像文件名走 contact_key）",
          P._safe_name("林静" + ZW) == core.contact_key("林静" + ZW))


def test_bound_persona():
    """风格绑定：原始键优先、归一化键兜底。"""
    print("\n[风格绑定查表]")
    cfg = {"personas": {"默认": "x", "亲密": "y"}, "contact_personas": {"苏晚 @云图设计": "亲密"}}
    eq("原始键命中", core.bound_persona(cfg, "苏晚 @云图设计"), "亲密")
    eq("归一化兜底命中（OCR 少个空格）", core.bound_persona(cfg, "苏晚@云图设计"), "亲密")
    eq("归一化兜底命中（尾随空格）", core.bound_persona(cfg, "苏晚 @云图设计 "), "亲密")
    eq("没绑定的返回 None", core.bound_persona(cfg, "别人"), None)
    eq("空表安全", core.bound_persona({}, "谁"), None)

    # 改写已有条目，不新增重复键
    core.set_bound_persona(cfg, "苏晚@云图设计", "默认")
    eq("改写而非新增", len(cfg["contact_personas"]), 1)
    eq("改写生效", core.bound_persona(cfg, "苏晚 @云图设计"), "默认")
    core.set_bound_persona(cfg, "新人", "亲密")
    eq("新人正常新增", cfg["contact_personas"].get("新人"), "亲密")


# ---------------------------------------------------------------- 画像读取
def _profile(name, obs, **kw):
    prof = P.blank(name)
    for o in obs:
        P._append(prof, o)
    prof.update(kw)
    P.save(prof)
    return prof


def test_load_hint_states():
    """五种「没带上画像」的原因必须能分开 —— 合并成一个，界面就只能说空话。"""
    print("\n[画像读取的五种状态]")
    _profile("有画像的", [{"kind": "关系事实", "text": "在建材行业",
                          "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    r = wx_ui.load_hint("有画像的")
    check("命中：有背景块", r["text"].startswith("\n\n") and "关于「对方」的背景" in r["text"],
          repr(r["text"][:30]))
    check("命中：注入前已 sanitize（不含【】）", "【" not in r["text"] and "】" not in r["text"], r["text"])
    check("命中：说明写清条数", "1 条观察" in r["why"], r["why"])
    eq("命中：状态是 hit", r["state"], "hit")
    eq("命中：条数上报", r["count"], 1)
    check("命中：不含联系人昵称", "有画像的" not in r["text"], r["text"])

    r = wx_ui.load_hint("从没建过的")
    eq("没建过：不带", r["text"], "")
    eq("没建过：条数 0", r["count"], 0)
    eq("没建过：状态是 none", r["state"], "none")
    check("没建过：说明是「还没建过」", "还没建过" in r["why"], r["why"])

    r = wx_ui.load_hint("")
    eq("没名字：不带", r["text"], "")
    eq("没名字：状态是 no_name", r["state"], "no_name")
    check("没名字：说明是「没识别到」", "没识别到" in r["why"], r["why"])

    # 空画像
    P.save(P.blank("空画像的"))
    r = wx_ui.load_hint("空画像的")
    eq("空画像：不带", r["text"], "")
    eq("空画像：状态是 empty", r["state"], "empty")
    check("空画像：说明是「空的」", "还是空的" in r["why"], r["why"])

    # 全待复核（旧「雷区」迁移）：load() 有值但一条都不该回喂
    old = {"schema": 1, "contact": "旧人", "stats": {"next_id": 2}, "observations": [
        {"id": "obs-0001", "kind": "雷区", "text": "旧雷区条目", "count": 1,
         "evidence": [{"quote": "q"}], "status": "active", "last_seen": "2026-09-01"}]}
    P.save(old)
    r = wx_ui.load_hint("旧人")
    eq("全待复核：不带", r["text"], "")
    eq("全待复核：条数 0", r["count"], 0)
    eq("全待复核：状态是 empty", r["state"], "empty")
    check("全待复核：说明写清「没有一条能回喂」", "没有一条能回喂" in r["why"], r["why"])

    # 全过期：非长期事实超过保鲜期
    stale = {"schema": 2, "contact": "过期的", "stats": {"next_id": 2}, "observations": [
        {"id": "obs-0001", "kind": "偏好话题", "text": "爱聊钓鱼", "count": 1,
         "evidence": [{"quote": "q"}], "status": "active", "last_seen": "2000-01-01"}]}
    P.save(stale)
    r = wx_ui.load_hint("过期的")
    eq("全过期：不带", r["text"], "")
    check("全过期：说明不是「没建过」", "还没建过" not in r["why"], r["why"])

    # 名字对不上但有相近的 → 必须提示 + 给确认入口，不能静默
    _profile("林静", [{"kind": "关系事实", "text": "在建材行业",
                      "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    r = wx_ui.load_hint("林静静")
    eq("OCR 认错名字：不带（绝不自动套用）", r["text"], "")
    eq("OCR 认错名字：状态是 similar", r["state"], "similar")
    eq("OCR 认错名字：给出候选名", r["guess"], "林静")
    check("OCR 认错名字：说明里点了名", "林静" in r["why"], r["why"])

    # 零宽差异属于「同一个人」，走归一命中，不该被当成 similar
    r = wx_ui.load_hint("有画像的" + ZW)
    eq("零宽差异仍命中（不是靠模糊匹配）", r["state"], "hit")


def test_hint_stats_counts():
    print("\n[背景块条数统计]")
    prof = {"contact": "x", "observations": [
        {"id": "obs-0001", "kind": "关系事实", "text": "在建材行业", "count": 1,
         "evidence": [{"quote": "q"}], "status": "active", "last_seen": "2026-09-01"},
        {"id": "obs-0002", "kind": "行为模式", "text": "问过见面时间", "count": 1,
         "evidence": [{"quote": "q"}], "status": "active", "last_seen": "2026-09-01"},
        {"id": "obs-0003", "kind": "行为模式", "text": "待复核的", "count": 1,
         "evidence": [{"quote": "q"}], "status": "review", "last_seen": "2026-09-01"},
    ]}
    text, used, total = P.hint_stats(prof)
    eq("带回 2 条（review 那条不算）", used, 2)
    eq("总数是全部条目", total, 3)
    eq("hint() 是 hint_stats 的薄封装", P.hint(prof), text)


# ---------------------------------------------------------------- 改写提示词
def test_refinement_prompt():
    print("\n[改写提示词带画像]")
    import json
    base = wx_ui.refinement_prompt(["对方: 在吗"], "在的", "默认", "", "短一点")
    check("不带画像时没有那个字段", "对方背景" not in base, base)
    with_hint = wx_ui.refinement_prompt(["对方: 在吗"], "在的", "默认", "", "短一点",
                                        "【关于「对方」的背景】\n关系事实：在建材行业")
    data = json.loads(with_hint.split("\n", 1)[1])
    key = "对方背景（只作参考，不得写进回复）"
    check("画像单独一个字段", key in data, list(data))
    check("画像没被拼进改写要求",
          "在建材行业" not in data["改写要求"], data["改写要求"])


# ---------------------------------------------------------------- 读取流程
class FakeCore:
    """替掉 wx_helper 模块，让 worker 跑在受控的假模型上。"""
    HERE = _TMP

    def __init__(self, first, second=None, second_raises=None):
        self.first, self.second, self.second_raises = first, second, second_raises
        self.calls = []          # 每次调用的 (有没有图, deadline)
        self.logs = []

    def log(self, msg):
        self.logs.append(msg)

    # 名字归一与风格绑定不测假货，直接转发真实实现 —— 被测的正是它们。
    bound_persona = staticmethod(core.bound_persona)
    set_bound_persona = staticmethod(core.set_bound_persona)

    def find_wechat(self):
        return "ok", 1

    def grab(self, hwnd):
        return "IMAGE"

    def crop_chat(self, image, cfg):
        return image

    def to_jpeg_b64(self, image):
        return "B64"

    def build_prompt(self, cfg, persona, nudge):
        return "READ_PROMPT"

    def build_text_prompt(self, cfg, messages, persona, nudge=""):
        self.last_text_prompt = nudge
        return "TEXT_PROMPT"

    def parse_reply(self, text):
        if text == "READ_PROMPT":
            return self.first
        return self.second if isinstance(self.second, dict) else {"candidates": self.second or []}

    def call_model(self, cfg, key, b64, prompt, cancel_event=None, system=None, deadline=None):
        self.calls.append((bool(b64), deadline, time.monotonic()))
        if b64:
            return "READ_PROMPT", None
        if self.second_raises:
            return "", self.second_raises
        return "TEXT_PROMPT", None


def _app(fake):
    cfg = {"personas": {"默认": "口语化", "亲密": "放松"}, "default_persona": "默认",
           "candidates": 3, "contact_personas": {}, "save_debug": False}
    app = wx_ui.ReplyApp(core, cfg, "KEY", testing=True)
    app.core = fake
    return app


def _run_read(app, name="某人", messages=None):
    payload = {"cfg": dict(app.cfg), "goal": "", "context": None, "cards": [],
               "persona": "默认", "index": None, "instruction": ""}
    app.worker(1, threading.Event(), "read", payload)
    events = []
    while True:
        try:
            events.append(app.q.get_nowait())
        except queue.Empty:
            break
    return events


def _reset_aliases():
    """清掉别名表。别名是**跨测试残留**的状态：一个测试确认了「林静静 = 林静」，
    后面所有依赖「林静静 认不出来 → similar」的测试就全废了。
    main() 在每个测试前调它，测试之间才互不污染。
    """
    try:
        os.remove(P.ALIAS_PATH)
    except OSError:
        pass


def _first_of(events, kind):
    return next((v for _j, k, v in events if k == kind), None)


def _pump(app, events, job=None):
    """把 worker 产出的队列事件真的喂给 handle_event。

    worker 只往队列里放，界面状态是 handle_event 改的。测试里直接读队列就绕过了
    一半被测代码 —— 「界面显示什么」和「事件里有什么」是两件事。

    job 默认从事件自己身上取（handle_event 会因为 job != epoch 把事件丢掉，
    硬编码一个号会在换一批之后全部失效）。
    """
    if job is None:
        job = events[0][0] if events else app.epoch
    app.epoch = job
    for j, kind, value in events:
        app.handle_event(j, kind, value)


def _run_batch(app, job=2):
    payload = {"cfg": dict(app.cfg), "goal": "", "context": app.context,
               "cards": list(app.cards), "persona": app.persona.get(),
               "index": None, "instruction": ""}
    app.worker(job, threading.Event(), "batch", payload)
    return _drain(app)


def _drain(app):
    events = []
    while True:
        try:
            events.append(app.q.get_nowait())
        except queue.Empty:
            break
    return events


def _drain_until(app, kind, timeout=10.0):
    """等 worker 线程产出的某个事件。

    start() 会真的开线程（adopt 走的就是这条路），所以这里必须等而不是立刻读队列，
    否则测试会在事件到达之前就断言，变成随机红绿。
    """
    deadline = time.monotonic() + timeout
    events = []
    while time.monotonic() < deadline:
        events.extend(_drain(app))
        if any(k == kind for _j, k, _v in events):
            return events
        time.sleep(0.02)
    return events


def _buttons(widget, out=None):
    import tkinter as tk
    out = [] if out is None else out
    for child in widget.winfo_children():
        if isinstance(child, tk.Button):
            out.append(child)
        _buttons(child, out)
    return out


def _dialog(app):
    import tkinter as tk
    return next(w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel))


def _first_result():
    # 候选是 parse_reply 已经剥掉编号的形式（真实的 parse_reply 会 lstrip 掉 "1. "）
    return {"name": "某人", "kind": "单聊", "messages": ["对方: 在吗"],
            "candidates": ["【直接】在的"]}


def test_read_with_hint():
    print("\n[读取：有画像 → 补发第二轮]")
    _profile("某人", [{"kind": "关系事实", "text": "在建材行业",
                      "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    fake = FakeCore(_first_result(), second={"candidates": ["【借背景】在的，上次说的那批货"]})
    app = _app(fake)
    try:
        events = _run_read(app)
        eq("发了两次请求", len(fake.calls), 2)
        eq("第一次带图", fake.calls[0][0], True)
        eq("第二次不带图", fake.calls[1][0], False)
        check("两次共享同一个 deadline",
              fake.calls[0][1] is not None and fake.calls[0][1] == fake.calls[1][1],
              fake.calls)
        # 第二轮要有保底时间：共享预算被第一轮耗光时，它不该以「剩 1 秒」开局。
        # 否则「有画像」的联系人反而比「没画像」的更容易拿不到好结果。
        check("第二轮有保底预算（不会饿死）",
              fake.calls[1][1] - fake.calls[1][2] >= 14.5,
              "剩余 %.1f 秒" % (fake.calls[1][1] - fake.calls[1][2]))
        check("第二轮保底不会把总时长拖回 90 秒",
              fake.calls[1][1] - fake.calls[0][2] <= 60.5,
              "总预算 %.1f 秒" % (fake.calls[1][1] - fake.calls[0][2]))
        check("背景块进了第二轮提示词",
              "关于「对方」的背景" in fake.last_text_prompt,
              fake.last_text_prompt[:80])
        result, cards = _first_of(events, "read")
        eq("用的是第二轮候选", cards[0]["text"], "在的，上次说的那批货")
        eq("上报用上了画像", result["hint_used"], True)
        eq("上报条数", result["hint_count"], 1)
    finally:
        app.root.destroy()


def test_read_second_request_fails():
    """附加收益失败绝不能摧毁主功能 —— 第一轮的候选必须保住。"""
    print("\n[读取：第二轮挂了 → 保住第一轮]")
    _profile("某人", [{"kind": "关系事实", "text": "在建材行业",
                      "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    fake = FakeCore(_first_result(), second_raises="请求超时，请稍后重试")
    app = _app(fake)
    app.cfg["contact_personas"] = {"某人": "亲密"}
    try:
        events = _run_read(app)
        check("没有报错事件", _first_of(events, "error") is None, _first_of(events, "error"))
        result, cards = _first_of(events, "read")
        eq("第一轮候选被保住", cards[0]["text"], "在的")
        eq("如实上报没用上画像", result["hint_used"], False)
        check("说明里写清了失败原因", "第二次请求失败" in result["hint_why"], result["hint_why"])
        check("失败有记日志", any("第二次请求失败" in s for s in fake.logs), fake.logs)
        # 这批卡片确实是按默认风格生成的第一轮结果 —— 说在 why 里，那是「本批发生了什么」该待的地方。
        check("说清了这批是默认风格的", "默认风格" in result["hint_why"], result["hint_why"])
        # 但 persona_name 是**持久**状态（写进下拉框、又被 persona_changed 存回配置），
        # 绝不能因为一次网络抖动就重置：否则下拉框显示默认 → 换一批按默认生成 →
        # 下次重新读屏又变回亲密，风格在批次之间无理由地闪。
        eq("绑定风格没有被抖动抹掉", result["persona_name"], "亲密")
        eq("配置里的绑定还在", app.cfg["contact_personas"]["某人"], "亲密")
    finally:
        app.root.destroy()


def test_fallback_keeps_bound_style_for_next_batch():
    """回退之后「换一批」必须仍按绑定的风格生成 —— 这是界面与配置不自洽的那个 bug。

    先前回退分支把 persona 重置成默认值，于是下拉框显示「默认」，
    换一批就真的按默认风格发请求；而 cfg 里的绑定仍是「亲密」，
    下次重新读屏第二轮又用亲密。用户看到的是风格在批次之间无理由地跳。
    """
    print("\n[回退之后换一批仍用绑定风格]")
    _profile("某人", [{"kind": "关系事实", "text": "在建材行业",
                      "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    fake = FakeCore(_first_result(), second_raises="请求超时，请稍后重试")
    app = _app(fake)
    app.cfg["contact_personas"] = {"某人": "亲密"}
    styles = []
    orig = fake.build_text_prompt

    def spy(cfg, messages, persona, nudge=""):
        styles.append(persona)
        return orig(cfg, messages, persona, nudge)
    fake.build_text_prompt = spy
    try:
        events = _run_read(app)
        _pump(app, events)
        eq("下拉框仍显示绑定的风格", app.persona.get(), "亲密")

        # 换一批：真的发一次请求，看它用哪个风格
        fake.second_raises = None
        fake.second = {"candidates": ["【直接】在的"]}
        _run_batch(app)
        check("换一批发过请求", styles, styles)
        eq("换一批用的是绑定的风格，不是默认", styles[-1], "放松")
    finally:
        app.root.destroy()


def test_read_second_request_empty():
    print("\n[读取：第二轮没给出候选 → 保住第一轮]")
    _profile("某人", [{"kind": "关系事实", "text": "在建材行业",
                      "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    fake = FakeCore(_first_result(), second={"candidates": []})
    app = _app(fake)
    try:
        events = _run_read(app)
        check("没有报错事件", _first_of(events, "error") is None, _first_of(events, "error"))
        result, cards = _first_of(events, "read")
        eq("第一轮候选被保住", cards[0]["text"], "在的")
        eq("如实上报没用上画像", result["hint_used"], False)
    finally:
        app.root.destroy()


def test_read_no_hint_no_extra_call():
    """空画像不该白发一次请求 —— 判据是背景块非空，不是画像文件存在。"""
    print("\n[读取：空画像 → 不补发]")
    old = {"schema": 1, "contact": "某人", "stats": {"next_id": 2}, "observations": [
        {"id": "obs-0001", "kind": "雷区", "text": "旧条目", "count": 1,
         "evidence": [{"quote": "q"}], "status": "active", "last_seen": "2026-09-01"}]}
    P.save(old)
    fake = FakeCore(_first_result())
    app = _app(fake)
    try:
        events = _run_read(app)
        eq("只发了一次请求", len(fake.calls), 1)
        result, cards = _first_of(events, "read")
        eq("第一轮候选照常显示", cards[0]["text"], "在的")
        eq("没声称用了画像", result["hint_used"], False)
        check("说清了为什么没带", "没有一条能回喂" in result["hint_why"], result["hint_why"])
    finally:
        app.root.destroy()


def test_read_bound_persona_survives_ocr_space():
    """致命项回归：OCR 多一个尾随空格，风格绑定不能丢。

    先前风格走精确 dict 查找、画像走 _safe_name 归一，两套不同源：
    '陈晓明 ' 查不到绑定 → persona 保持默认 → 判定「没有绑定非默认风格」→
    本该补发的画像请求不发，用户建了画像却完全用不上，且没有任何提示。
    """
    print("\n[读取：OCR 名字带尾随空格]")
    _profile("陈晓明", [{"kind": "关系事实", "text": "在建材行业",
                         "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    fake = FakeCore(dict(_first_result(), name="陈晓明 "),
                    second={"candidates": ["【借背景】在的"]})
    app = _app(fake)
    app.cfg["contact_personas"] = {"陈晓明": "亲密"}
    try:
        events = _run_read(app)
        result, _cards = _first_of(events, "read")
        eq("风格绑定没丢", result["persona_name"], "亲密")
        check("背景块真的进了提示词",
              "关于「对方」的背景" in fake.last_text_prompt, fake.last_text_prompt[:80])
        eq("画像也被用上", result["hint_used"], True)
        eq("发了两次请求", len(fake.calls), 2)
    finally:
        app.root.destroy()


def test_leaked_hint_filtered():
    print("\n[读取：背景块被吐回来 → 不当卡片]")
    _profile("某人", [{"kind": "关系事实", "text": "在建材行业",
                      "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    leaked = "【关于「对方」的背景】\n关系事实：在建材行业\n以上背景仅供参考；若与当前对话冲突，以当前对话为准。"
    fake = FakeCore(_first_result(), second={"candidates": [leaked, "【正常】在的"]})
    app = _app(fake)
    try:
        events = _run_read(app)
        _result, cards = _first_of(events, "read")
        eq("只剩一张卡片", len(cards), 1)
        eq("留下的是真回复", cards[0]["text"], "在的")
    finally:
        app.root.destroy()


def test_read_all_candidates_leaked_keeps_first():
    """第二轮只回吐背景块时，第一轮的有效候选必须保住。

    先前是「先替换、后过滤」：三条全被滤掉 → 走「没有有效候选」直接报错，
    第一轮明明有候选却被丢了，和「附加收益失败绝不摧毁主功能」正好相反。
    """
    print("\n[读取：第二轮全是背景块 → 保住第一轮]")
    _profile("某人", [{"kind": "关系事实", "text": "在建材行业",
                      "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    fake = FakeCore(_first_result(), second={"candidates": ["【关于「对方」的背景】x"]})
    app = _app(fake)
    app.cfg["contact_personas"] = {"某人": "亲密"}
    try:
        events = _run_read(app)
        check("没有报错事件", _first_of(events, "error") is None, _first_of(events, "error"))
        result, cards = _first_of(events, "read")
        eq("第一轮候选被保住", cards[0]["text"], "在的")
        eq("如实上报没用上画像", result["hint_used"], False)
        check("说清是第二轮吐回了背景块", "背景块" in result["hint_why"], result["hint_why"])
        # 与 test_read_second_request_fails 对称：两条回退路径都不许重置绑定风格
        # （persona_name 是持久的，重置会让下拉框在批次之间无理由地闪）。
        eq("绑定风格没被回退抹掉", result["persona_name"], "亲密")
    finally:
        app.root.destroy()


def test_read_no_candidates_at_all_errors():
    """两轮都没候选，才是真失败 —— 该报错而不是给一片空白。"""
    print("\n[读取：两轮都没候选 → 报错]")
    _profile("某人", [{"kind": "关系事实", "text": "在建材行业",
                      "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    fake = FakeCore(dict(_first_result(), candidates=[]),
                    second={"candidates": ["【关于「对方」的背景】x"]})
    app = _app(fake)
    try:
        events = _run_read(app)
        check("报了错", _first_of(events, "error") is not None)
    finally:
        app.root.destroy()


# ---------------------------------------------------------------- 画像窗口
def test_profile_window_builds():
    print("\n[画像窗口]")
    _profile("窗口测试", [{"kind": "关系事实", "text": "在建材行业",
                          "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    from profile_ui import ProfileWindow
    app = _app(FakeCore(_first_result()))
    win = None
    try:
        win = ProfileWindow(app)
        check("窗口建起来了", win.top.winfo_exists())
        check("标题不含联系人名", "窗口测试" not in win.top.title(), win.top.title())
        check("默认不显示原话", win.show_quotes.get() is False)
        win.switch("view")
        win.select("窗口测试")
        check("画像页能渲染", bool(win.observations))
        win.show_quotes.set(True)
        win.render_profile()
        check("勾上后能显示原话", bool(win.observations))
        win.prefill("带过来的名字")
        eq("主窗口认出的名字被带过来", win.name_var.get(), "带过来的名字")
    finally:
        if win is not None:
            win.close()
        app.root.destroy()


def test_profile_window_reject():
    print("\n[画像窗口：点「不准」]")
    _profile("删除测试", [{"kind": "关系事实", "text": "在建材行业",
                          "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    from profile_ui import ProfileWindow
    app = _app(FakeCore(_first_result()))
    win = None
    try:
        win = ProfileWindow(app)
        win.select("删除测试")
        obs_id = win.observations[0]["id"]
        win.reject_one(obs_id)
        eq("条目被删掉", len(P.load("删除测试")["observations"]), 0)
        check("进了黑名单", "在建材行业" in P.rejected_list())
    finally:
        if win is not None:
            win.close()
        app.root.destroy()


def test_heal_old_entries():
    """旧画像条目缺字段不能让整个画像页打不开。

    真跑出来的：手工/旧版本写下的条目没有 confidence，profile_ui 直接 o["confidence"]
    → KeyError → 用户看到的是「读不到画像」，而不是「有条目缺字段」。
    """
    print("\n[旧条目缺字段自愈]")
    broken = {"schema": 1, "contact": "缺字段的", "stats": {}, "observations": [
        {"id": "obs-0001", "kind": "关系事实", "text": "在建材行业",
         "evidence": [{"quote": "q"}]}]}
    P.save(broken)
    prof = P.load("缺字段的")
    o = prof["observations"][0]
    eq("补上 confidence", o["confidence"], "低")
    eq("补上 count", o["count"], 1)
    eq("补上 status", o["status"], "active")
    eq("补上 contradicts", o["contradicts"], [])
    check("补上 last_seen", "last_seen" in o)
    check("还能正常回喂", bool(P.hint(prof)))

    # 连 evidence 都没有的条目也不能炸
    worse = {"schema": 1, "contact": "更破的", "stats": {}, "observations": [
        {"id": "obs-0001", "kind": "行为模式", "text": "x"}]}
    P.save(worse)
    o2 = P.load("更破的")["observations"][0]
    eq("evidence 补成空列表", o2["evidence"], [])
    eq("count 至少是 1", o2["count"], 1)


def test_merge_reports_new_evidence():
    """重复粘贴同一段聊天：合并数 > 0 但新证据 0 —— 界面必须能分开说。"""
    print("\n[合并 vs 新证据]")
    prof = P.blank("重复粘贴")
    obs = [{"kind": "行为模式", "text": "问过见面时间",
            "evidence": [{"quote": "下次啥时候", "at": "2026-09-01"}]}]

    class M:
        @staticmethod
        def call_model(cfg, key, b64, prompt, cancel_event=None, system=None):
            return ('{"ops":[{"new_index":0,"op":"merge","target":"obs-0001"}]}', None)

    a, m, c, ev = P.merge_with_evidence(M, {}, "", prof, obs)
    eq("首次：新增 1 条", (a, m, c), (1, 0, 0))
    eq("首次：新证据 1 条", ev, 1)

    a, m, c, ev = P.merge_with_evidence(M, {}, "", prof, obs)
    eq("重复：走了合并", m, 1)
    eq("重复：新证据 0 条", ev, 0)

    a, m, c, ev = P.merge_with_evidence(M, {}, "", prof, [{"kind": "行为模式", "text": "问过见面时间",
                                                          "evidence": [{"quote": "这周有空吗"}]}])
    eq("真新证据：合并 1 条", m, 1)
    eq("真新证据：新证据 1 条", ev, 1)

    check("merge() 仍是三元组（CLI 和测试不受影响）",
          len(P.merge(M, {}, "", prof, [])) == 3)


def test_similar_state_does_not_use_other_profile():
    """OCR 认错名字时绝不自动套用别人的画像 —— 用错人比不用更糟。"""
    print("\n[读取：名字对不上 → 不自动套用]")
    _profile("林静", [{"kind": "关系事实", "text": "在建材行业",
                      "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    fake = FakeCore(dict(_first_result(), name="林静静"))
    app = _app(fake)
    try:
        events = _run_read(app)
        result, _cards = _first_of(events, "read")
        eq("没带画像", result["hint_used"], False)
        eq("状态是 similar", result["hint_state"], "similar")
        eq("给出候选名", result["hint_guess"], "林静")
        eq("只发一次请求（没有白花第二次）", len(fake.calls), 1)
    finally:
        app.root.destroy()


def test_confirm_similar_name_uses_profile_now():
    """「就是这个人，用他的画像」：确认之后**本次**就要用上画像。

    这条路径是「名字对不上」唯一的出口 —— 只提示不给入口等于没提示。
    而且确认的收益必须落在本次：让用户改完名字再按一次热键，
    等于把「确认是同一个人」的收益推到了下一次。
    """
    print("\n[确认同一个人：记别名 + 本次就用上画像]")
    _profile("林静", [{"kind": "关系事实", "text": "在建材行业",
                      "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    fake = FakeCore(dict(_first_result(), name="林静静"),
                    second={"candidates": ["【借背景】在的，上次说的那批货"]})
    app = _app(fake)
    try:
        events = _run_read(app, name="林静静")
        result, _cards = _first_of(events, "read")
        eq("先是不带画像", result["hint_state"], "similar")
        _pump(app, events)

        app.show_context()
        btn = next(b for b in _buttons(_dialog(app)) if "就是这个人" in b.cget("text"))
        btn.invoke()

        eq("记下了别名", P.aliases().get("林静静"), "林静")
        eq("名字换成了画像名", app.context["name"], "林静")
        # 关键：不是「下次生效」，是这次就生效 —— 弹窗里的状态已经是 hit
        eq("本次就用上了画像", app.context["hint_state"], "hit")
        check("grab 已释放（否则 start 会被自己拒绝）",
              app.root.grab_current() is None, app.root.grab_current())
        eq("真的发起了重新生成", app.busy, True)
        check("没有卡在「请先完成或关闭编辑窗口」",
              "请先完成" not in app.status.cget("text"), app.status.cget("text"))

        # 等真线程跑完：确认之后这一批拿到的应该是带画像的第二轮结果。
        # 这一步必须真的走完，否则留一个在跑的线程给后面的测试。
        events2 = _drain_until(app, "batch")
        got = _first_of(events2, "batch")
        check("重新生成了卡片", got is not None, _first_of(events2, "error"))
        if got:
            eq("用的是画像那一轮的结果", got[0]["text"], "在的，上次说的那批货")
        check("背景块进了提示词",
              "关于「对方」的背景" in fake.last_text_prompt, fake.last_text_prompt[:80])
    finally:
        app.root.destroy()


def test_batch_emits_hint_state():
    """「换一批」要重新上报「这次带没带画像」。

    用户刚在弹窗里确认了「就是这个人」，接着点「换一批」——
    如果 batch 不上报 hint 状态，meta 行还停在上一批的「没带画像」，
    界面就在骗人：明明带上了却说没带。
    """
    print("\n[换一批：重新上报画像状态]")
    _profile("某人", [{"kind": "关系事实", "text": "在建材行业",
                      "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    fake = FakeCore(_first_result(), second={"candidates": ["【借背景】在的"]})
    app = _app(fake)
    try:
        events = _run_read(app)
        _pump(app, events)
        # 先把它改成「没带画像」，模拟上一批的状态
        app.context.update(hint_used=False, hint_count=0, hint_state="none", hint_why="")
        events2 = _run_batch(app)
        hint_ev = _first_of(events2, "hint")
        check("batch 发了 hint 事件", hint_ev is not None, [k for _j, k, _v in events2])
        if hint_ev:
            eq("上报带了画像", hint_ev["used"], True)
            eq("上报条数", hint_ev["count"], 1)
            eq("状态是 hit", hint_ev["state"], "hit")
        _pump(app, events2)
        eq("context 跟着更新了", app.context["hint_used"], True)
        check("meta 行不再说没带", "画像 1 条" in app.meta.cget("text"), app.meta.cget("text"))
    finally:
        app.root.destroy()


def test_rename_recomputes_hint_state():
    """在弹窗里把名字改成一个**有画像**的名字，状态要跟着变成「带上了」。

    先前一律清成「没带」：用户明明改对了名字，界面却说没带画像，
    接着点「换一批」也就真的不带了 —— 改名字这件事白做。
    """
    print("\n[弹窗里改名字 → 重算画像状态]")
    _profile("陈晓明", [{"kind": "关系事实", "text": "在建材行业",
                         "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    fake = FakeCore(dict(_first_result(), name="陈晓"))
    app = _app(fake)
    try:
        events = _run_read(app, name="陈晓")
        result, _cards = _first_of(events, "read")
        eq("读的时候没带（名字对不上）", result["hint_used"], False)
        _pump(app, events)

        app.show_context()
        import tkinter as tk
        entry = next(w for w in _dialog(app).winfo_children()
                     if isinstance(w, tk.Frame))
        # 直接改 StringVar：entry 的 textvariable 就是它
        var = None
        for w in _buttons(_dialog(app)):
            pass
        # 通过遍历找到那个 Entry 绑定的变量
        def find_entry(w):
            for c in w.winfo_children():
                if isinstance(c, tk.Entry):
                    return c
                r = find_entry(c)
                if r is not None:
                    return r
            return None
        e = find_entry(_dialog(app))
        check("找到了名字输入框", e is not None)
        if e is not None:
            e.delete(0, "end")
            e.insert(0, "陈晓明")
        next(b for b in _buttons(_dialog(app)) if "保存纠正" in b.cget("text")).invoke()
        eq("改名后重算出「带上了」", app.context["hint_used"], True)
        eq("状态是 hit", app.context["hint_state"], "hit")
        eq("名字已更新", app.context["name"], "陈晓明")
        # 而且本次的「换一批」就该带上
        events2 = _run_batch(app)
        check("换一批带上了背景块",
              "关于「对方」的背景" in fake.last_text_prompt, fake.last_text_prompt[:80])
    finally:
        app.root.destroy()


def _listbox(parent):
    """弹窗里的候选列表。找不到返回 None。"""
    import tkinter as tk
    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, tk.Listbox):
                return c
            r = walk(c)
            if r is not None:
                return r
        return None
    return walk(parent)


def _pick_item(parent, text):
    """选中列表里那一项。

    弹窗默认选第一项，而候选是**整个临时目录**里的画像 —— 测试之间会互相攒，
    第一项根本不是这条测试想并的那份。必须按名字显式选，
    否则测的是「碰巧排第一的那个」。
    """
    lb = _listbox(parent)
    check("找到了候选列表", lb is not None)
    if lb is None:
        return None
    items = list(lb.get(0, "end"))
    if text not in items:
        print("      DEBUG 列表里实际有：%r" % (items,))
        check("列表里有「%s」" % text, False)
        return None
    lb.selection_clear(0, "end")
    lb.selection_set(items.index(text))
    return lb


def test_profile_window_merge_contact():
    """「并入另一个画像…」：OCR 认错名字攒下两份画像时，唯一能把它们合起来的入口。

    这条路径此前一个断言都没有 —— 而它是 merge_contact() 唯一的生产调用方，
    也是「两份画像都在、谁也不会自动合并」这个僵局的唯一出口。
    """
    print("\n[画像窗口：并入另一个画像]")
    _profile("合并目标", [{"kind": "关系事实", "text": "在建材行业",
                        "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    _profile("合并源", [{"kind": "行为模式", "text": "回消息慢",
                       "evidence": [{"quote": "我最近忙", "at": "2026-09-01"}]}])
    from profile_ui import ProfileWindow
    import tkinter as tk
    app = _app(FakeCore(_first_result()))
    win = None
    try:
        win = ProfileWindow(app)
        win.select("合并目标")
        before = [f for f in os.listdir(P.PROFILE_DIR) if f.endswith(".merged")]
        btn = next(b for b in _buttons(win.top) if "并入另一个画像" in b.cget("text"))
        btn.invoke()
        top = next(w for w in win.top.winfo_children() if isinstance(w, tk.Toplevel))
        eq("弹窗标题", top.title(), "并入另一个画像")
        _pick_item(top, "合并源")
        go = next(b for b in _buttons(top) if b.cget("text") == "并入")
        go.invoke()

        known = P.known_contacts()
        check("源画像从列表里消失", "合并源" not in known, known)
        check("目标还在", "合并目标" in known, known)
        eq("观察被并进来了", len(P.load("合并目标")["observations"]), 2)
        check("状态栏说清了从哪并来的",
              "合并源" in win.status.cget("text"), win.status.cget("text"))
        # 被并的那份是**改名**不是删除：用户反悔了还能自己找回文件
        after = [f for f in os.listdir(P.PROFILE_DIR) if f.endswith(".merged")]
        eq("多出一份 .merged（没删）", len(after), len(before) + 1)
    finally:
        if win is not None:
            win.close()
        app.root.destroy()


def test_profile_window_merge_empty_source():
    """源画像一条观察都没有时，也要说清「它已经并掉了」，不能说「没并进任何东西」。

    界面若只说「没并进任何东西」，用户会以为操作失败 —— 而列表里那份已经不见了。
    """
    print("\n[画像窗口：并入一份空画像]")
    _profile("空并目标", [{"kind": "关系事实", "text": "在建材行业",
                        "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    P.save(P.blank("空并源"))
    from profile_ui import ProfileWindow
    import tkinter as tk
    app = _app(FakeCore(_first_result()))
    win = None
    try:
        win = ProfileWindow(app)
        win.select("空并目标")
        next(b for b in _buttons(win.top) if "并入另一个画像" in b.cget("text")).invoke()
        top = next(w for w in win.top.winfo_children() if isinstance(w, tk.Toplevel))
        _pick_item(top, "空并源")
        next(b for b in _buttons(top) if b.cget("text") == "并入").invoke()
        known = P.known_contacts()
        check("源从列表消失", "空并源" not in known, known)
        check("说清了它已改名，不是「什么都没发生」",
              ".merged" in win.status.cget("text"), win.status.cget("text"))
    finally:
        if win is not None:
            win.close()
        app.root.destroy()


def test_merge_dialog_lists_every_candidate():
    """候选**一个都不能少**：想并的那份排在后面就不显示，用户只会以为它不存在。

    原来只取 others[:8] 且没有任何提示 —— 而画像多起来恰恰是这条路径要解决的场景。

    这里刻意用**名字很长**的凑数项：换成 Listbox 之后，短名字凑到第 9 个也不会
    被截断，`others[:8]` 这种变异照样能全绿 —— 那这条断言就只是「今天恰好没红」。
    长名字让条目真的排到可视区之外，截断才会以「列表里根本没有这一项」的形式暴露。
    """
    print("\n[画像窗口：并入弹窗列全候选]")
    _profile("全列目标", [{"kind": "关系事实", "text": "在建材行业",
                        "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    for i in range(12):
        P.save(P.blank("凑数联系人%02d·备注很长的名字" % i))
    from profile_ui import ProfileWindow
    import tkinter as tk
    app = _app(FakeCore(_first_result()))
    win = None
    try:
        win = ProfileWindow(app)
        win.select("全列目标")
        want = [n for n in P.known_contacts() if n != "全列目标"]
        eq("候选确实超过 8 份", len(want) > 8, True)
        next(b for b in _buttons(win.top) if "并入另一个画像" in b.cget("text")).invoke()
        top = next(w for w in win.top.winfo_children() if isinstance(w, tk.Toplevel))
        lb = _listbox(top)
        check("弹窗里有列表", lb is not None)
        if lb is not None:
            got = list(lb.get(0, "end"))
            eq("列出的份数", len(got), len(want))
            eq("没有截断", sorted(got), sorted(want))
            check("排在最后的那份也在列表里", want[-1] in got, want[-1])
            # 并且**能真的选中并并掉** —— 只断言「在列表里」的话，
            # 一个把 curselection 忽略掉的 go() 仍然全绿。
            _pick_item(top, want[-1])
            next(b for b in _buttons(top) if b.cget("text") == "并入").invoke()
            check("末尾那份真的并掉了", want[-1] not in P.known_contacts(), P.known_contacts())
    finally:
        if win is not None:
            win.close()
        app.root.destroy()


def test_profile_window_handles_broken_entries():
    print("\n[画像窗口：旧条目缺字段也能打开]")
    broken = {"schema": 1, "contact": "破画像", "stats": {}, "observations": [
        {"id": "obs-0001", "kind": "关系事实", "text": "在建材行业",
         "evidence": [{"quote": "q"}]}]}
    P.save(broken)
    from profile_ui import ProfileWindow
    app = _app(FakeCore(_first_result()))
    win = None
    try:
        win = ProfileWindow(app)
        win.select("破画像")
        check("画像页渲染出来了", len(win.observations) == 1)
    finally:
        if win is not None:
            win.close()
        app.root.destroy()


def test_profile_window_asks_before_similar_name():
    """名字很像时不能直接开始跑，要先问一句 —— 状态栏的提示会被下一句盖掉。"""
    print("\n[画像窗口：名字很像 → 先确认]")
    _profile("林静", [{"kind": "关系事实", "text": "在建材行业",
                      "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    from profile_ui import ProfileWindow
    app = _app(FakeCore(_first_result()))
    win = None
    try:
        win = ProfileWindow(app)
        win.name_var.set("林静静")
        win.text.insert("1.0", "林静: 在忙吗\n我: 刚下班\n")
        win.start_extract()
        eq("没有直接开跑", win.busy, False)
        check("状态栏在问", "很像" in win.status.cget("text"), win.status.cget("text"))
        eq("记住了待确认的名字", win.pending_name, "林静静")
        # 用户确认是两个人 → 再点一次就开跑
        win.start_extract()
        eq("确认后开跑", win.busy, True)
        win.cancel()
    finally:
        if win is not None:
            win.close()
        app.root.destroy()


def test_profile_window_use_known_clears_pending():
    print("\n[画像窗口：点已有名字 = 确认同一个人]")
    _profile("林静", [{"kind": "关系事实", "text": "在建材行业",
                      "evidence": [{"quote": "我在建材行业", "at": "2026-09-01"}]}])
    from profile_ui import ProfileWindow
    app = _app(FakeCore(_first_result()))
    win = None
    try:
        win = ProfileWindow(app)
        win.name_var.set("林静静")
        win.text.insert("1.0", "林静: 在忙吗\n我: 刚下班\n")
        win.start_extract()
        eq("进入待确认", win.pending_name, "林静静")
        win.use_known("林静")
        eq("名字被换成已有画像名", win.name_var.get(), "林静")
        eq("待确认被清掉", win.pending_name, "")
        win.start_extract()
        eq("这次直接开跑", win.busy, True)
        win.cancel()
    finally:
        if win is not None:
            win.close()
        app.root.destroy()


def main():
    print("界面接线回归测试（临时目录：%s）" % _TMP)
    try:
        _reset_aliases()
        test_contact_key()
        test_bound_persona()
        test_load_hint_states()
        test_hint_stats_counts()
        test_refinement_prompt()
        test_heal_old_entries()
        test_merge_reports_new_evidence()
        test_read_with_hint()
        test_read_second_request_fails()
        test_fallback_keeps_bound_style_for_next_batch()
        test_read_second_request_empty()
        test_read_no_hint_no_extra_call()
        test_read_bound_persona_survives_ocr_space()
        test_similar_state_does_not_use_other_profile()
        test_leaked_hint_filtered()
        test_read_all_candidates_leaked_keeps_first()
        test_read_no_candidates_at_all_errors()
        test_confirm_similar_name_uses_profile_now()
        test_batch_emits_hint_state()
        test_rename_recomputes_hint_state()
        test_profile_window_builds()
        test_profile_window_reject()
        test_profile_window_merge_contact()
        test_profile_window_merge_empty_source()
        test_merge_dialog_lists_every_candidate()
        test_profile_window_handles_broken_entries()
        _reset_aliases()          # 前面的测试可能记过别名，别污染下面的 similar 判定
        test_profile_window_asks_before_similar_name()
        _reset_aliases()
        test_profile_window_use_known_clears_pending()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)

    print("\n" + "=" * 50)
    if FAILED:
        print("失败 %d 项：" % len(FAILED))
        for f in FAILED:
            print("  - " + f)
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
