# -*- coding: utf-8 -*-
"""Local-only tests for the optional Jev advisor.  No network calls."""
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import jev_advisor as J


def eq(name, got, want):
    if got != want:
        raise AssertionError("%s: got %r, want %r" % (name, got, want))


def test_payload():
    cards = [
        {"label": "直接", "text": "可以，明天下午三点。"},
        {"label": "留余地", "text": "我先确认一下时间，晚点回复你。"},
    ]
    payload = J.build_payload(["对方: 明天下午能见吗？"], cards, "先别承诺",
                              "表达方式：喜欢先确认时间")
    eq("model", payload["model"], "jev-latest")
    eq("message", payload["state"]["recent_messages"], ["对方: 明天下午能见吗？"])
    eq("candidate ids", [x["id"] for x in payload["state"]["reply_options"]],
       ["option_1", "option_2"])
    eq("profile digest", payload["state"]["profile_digest"], "表达方式：喜欢先确认时间")
    eq("none fallback", "none" in payload["questions"]["best_reply"]["criteria"], True)
    eq("all judgments", set(payload["questions"]), {
        "incoming_intent", "emotional_tone", "conflict_risk", "reply_timing",
        "profile_relevance", "candidate_diversity", "best_reply",
    })


def test_high_confidence():
    data = {"answers": {
        "incoming_intent": {"choice": "coordinate_next_step", "confidence": 0.84,
                            "probabilities": {"coordinate_next_step": 0.9}},
        "emotional_tone": {"choice": "anxious", "confidence": 0.72},
        "conflict_risk": {"score": 1.1, "confidence": 0.68},
        "reply_timing": {"choice": "reply_today", "confidence": 0.75},
        "profile_relevance": {"choice": "relevant", "confidence": 0.83},
        "candidate_diversity": {"choice": "mostly_same", "confidence": 0.79},
        "best_reply": {"choice": "option_2", "confidence": 0.73,
                       "probabilities": {"option_1": 0.12, "option_2": 0.78,
                                         "none": 0.10}},
    }}
    got = J.parse_response(data, 2, threshold=0.55)
    eq("intent", got["intent"], "协商下一步")
    eq("emotion", got["emotion"], "焦虑")
    eq("conflict", got["conflict_risk"], "中")
    eq("timing", got["timing"], "建议今天回复")
    eq("profile relevance", got["profile_relevance"], "相关")
    eq("diversity", got["candidate_diversity"], "角度较接近")
    eq("duplicate warning", got["duplicate_warning"], True)
    eq("recommended", got["recommended_index"], 1)
    eq("probability", got["recommendation_probability"], 0.78)


def test_low_confidence_suppresses_recommendation():
    data = {"answers": {
        "incoming_intent": {"choice": "request_action", "confidence": 0.3},
        "emotional_tone": {"choice": "angry", "confidence": 0.2},
        "conflict_risk": {"score": 1.8, "confidence": 0.3},
        "reply_timing": {"choice": "reply_now", "confidence": 0.2},
        "profile_relevance": {"choice": "relevant", "confidence": 0.1},
        "candidate_diversity": {"choice": "mostly_same", "confidence": 0.2},
        "best_reply": {"choice": "option_1", "confidence": 0.2,
                       "probabilities": {"option_1": 0.4, "option_2": 0.35,
                                         "none": 0.25}},
    }}
    got = J.parse_response(data, 2, threshold=0.55)
    eq("unclear intent", got["intent"], "意图暂不明确")
    eq("emotion hidden", got["emotion"], None)
    eq("conflict hidden", got["conflict_risk"], None)
    eq("timing hidden", got["timing"], None)
    eq("profile hidden", got["profile_relevance"], None)
    eq("duplicate hidden", got["duplicate_warning"], False)
    eq("no recommendation", got["recommended_index"], None)


def test_cancelled_never_reads_key_or_calls_network():
    old = J.load_key
    try:
        J.load_key = lambda _cfg: (_ for _ in ()).throw(AssertionError("should not load key"))
        event = threading.Event()
        event.set()
        got = J.advise({"jev_enabled": True}, ["x"], [{"text": "a"}, {"text": "b"}],
                       cancel_event=event)
        eq("cancelled", got, None)
    finally:
        J.load_key = old


def main():
    test_payload()
    test_high_confidence()
    test_low_confidence_suppresses_recommendation()
    test_cancelled_never_reads_key_or_calls_network()
    print("test_jev: OK")


if __name__ == "__main__":
    main()
