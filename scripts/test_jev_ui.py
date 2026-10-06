# -*- coding: utf-8 -*-
"""Local-only rendering checks for the compact/expanded Jev panel."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import test_ui as T


def texts(widget, out=None):
    out = out if out is not None else []
    try:
        value = widget.cget("text")
        if value:
            out.append(str(value))
    except Exception:
        pass
    for child in widget.winfo_children():
        texts(child, out)
    return out


def check(name, value):
    if not value:
        raise AssertionError(name)


def main():
    app = T._app(T.FakeCore(T._first_result()))
    try:
        app.cards = [
            {"label": "直接", "text": "可以，明天下午见。"},
            {"label": "留余地", "text": "我先确认一下再回复你。"},
            {"label": "改时间", "text": "明天不方便，后天可以吗？"},
        ]
        app.context = {"name": "某人", "kind": "单聊", "messages": ["对方: 明天见吗"],
                       "read_at": "12:00:00", "persona_name": "默认",
                       "hint_used": True, "hint_count": 2}
        app.jev_advice = {
            "intent": "协商下一步", "intent_confidence": 0.84,
            "emotion": "焦虑", "emotion_confidence": 0.72,
            "conflict_risk": "中", "timing": "建议今天回复", "timing_confidence": 0.75,
            "profile_relevance": "相关", "candidate_diversity": "角度较接近",
            "duplicate_warning": True, "recommended_index": 1,
            "recommendation_probability": 0.78,
        }
        app.render_advice()
        app.render_cards()
        compact = "\n".join(texts(app.advice_box))
        check("compact intent", "可能诉求：协商下一步" in compact)
        check("compact emotion", "情绪：焦虑（冲突风险中）" in compact)
        check("compact timing", "时机：建议今天回复" in compact)
        check("recommendation", "推荐「留余地」（匹配度 78%）" in compact)
        check("duplicate warning", "候选表达角度较接近" in compact)
        check("details initially hidden", "画像相关性" not in compact)
        check("card badge", "Jev 推荐" in "\n".join(texts(app.card_box)))
        app.toggle_advice_details()
        expanded = "\n".join(texts(app.advice_box))
        check("expanded details", "画像相关性：相关" in expanded)
        app.handle_event(app.epoch, "jev", app.jev_advice)
        check("profile meta", "画像 2 条·相关" in app.meta.cget("text"))
        print("test_jev_ui: OK")
    finally:
        app.close()


if __name__ == "__main__":
    main()
