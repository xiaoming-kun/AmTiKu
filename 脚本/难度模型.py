#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""题目级难度模型 v1：用 3,687 条人工难度，把“考点=一律难题”拆开。

## 为什么不是直接把 29k 道丢给大模型

没有校准集时，模型说“这道是难题”你无法判断它准不准。这里先用人工标签
做 5 折交叉验证（按题随机 / 按考点分组两种），只有**随机折准确率 ≥ 0.68**
才允许写回；写回时只写**置信度 ≥ 0.6** 的题，其余继续按考点派生。
低置信的题不是丢了，而是留给人工复核（见报告里的“待复核”数）。

## 特征

题干/解析的字符 2–3 gram TF-IDF + 少量结构化特征：
长度、选项数、有图、小问数、公式/根号/积分个数、题型、年份、
主考点自带的难度先验、原卷题号/卷内位置。
`LogisticRegression(class_weight=balanced)`——3,687 行、3 万维稀疏特征，
线性模型比树模型稳，也更容易解释。

用法：

    python3 脚本/难度模型.py                  # 只训练 + 交叉验证，不写库
    python3 脚本/难度模型.py --apply          # 写回高置信预测
    python3 脚本/难度模型.py --apply --min-conf 0.7
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import GroupKFold, StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import knowledge, store  # noqa: E402

LABELS = ("简单题", "中档题", "难题")
Y = {k: i for i, k in enumerate(LABELS)}
PRIOR = {"简单题": 1, "中档题": 2, "难题": 3}


def text_of(q) -> str:
    return ((q.stem or "") + " " + (q.solution or "")).strip()


def num_of(q) -> list[float]:
    s, sol = q.stem or "", q.solution or ""
    try:
        no = int(q.meta.get("source_no") or 0)
    except (TypeError, ValueError):
        no = 0
    try:
        ps = int(q.meta.get("paper_group_size") or 0)
    except (TypeError, ValueError):
        ps = 0
    try:
        pi = int(q.meta.get("paper_group_index") or 0)
    except (TypeError, ValueError):
        pi = 0
    prior = PRIOR.get(knowledge.difficulty_of(q.points[0]) if q.points else "", 0)
    return [
        len(s) ** 0.5, len(sol) ** 0.5, len(sol) / max(1, len(s)),
        len(q.options), int(bool(q.figures)),
        s.count("\\item"), s.count("$") / 2, s.count("\\frac"),
        s.count("\\sqrt"), s.count("\\int"), s.count("\\sum"),
        int(q.type == "single_choice"), int(q.type == "multi_choice"),
        int(q.type == "fill_in_blank"), int(q.type == "detailed_answer"),
        int(q.kind == "高考"), float(q.meta.get("year") or 0), prior,
        no, ps, pi, (no / ps if ps else 0),
    ]


def build():
    qs = store.load_all()
    lab = [q for q in qs if q.meta.get("difficulty") in LABELS]
    if len(lab) < 500:
        raise SystemExit("人工难度少于 500 条，先补标签再训练")
    vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), min_df=3,
                          max_features=30000, sublinear_tf=True)
    # 词表在**全库**上拟合（无监督，不偷标签），这样预测 29k 时不会满屏 OOV
    vec.fit([text_of(q) for q in qs])
    Xtxt_all = vec.transform([text_of(q) for q in qs])
    num_lab = np.array([num_of(q) for q in lab], dtype=float)
    scaler = StandardScaler().fit(num_lab)
    Xnum_lab = scaler.transform(num_lab)
    Xnum_all = scaler.transform(np.array([num_of(q) for q in qs], dtype=float))
    kpos = {q.key: i for i, q in enumerate(qs)}
    X_lab = hstack([csr_matrix(Xnum_lab),
                    Xtxt_all[[kpos[q.key] for q in lab]]]).tocsr()
    X_all = hstack([csr_matrix(Xnum_all), Xtxt_all]).tocsr()
    y = np.array([Y[q.meta["difficulty"]] for q in lab])
    groups = np.array([q.points[0] if q.points else "" for q in lab])
    return qs, lab, X_lab, X_all, y, groups


def train_and_report(lab, X_lab, y, groups):
    clf = LogisticRegression(max_iter=2000, C=2, class_weight="balanced")
    out = {}
    for name, cv in (("random", StratifiedKFold(5, shuffle=True, random_state=0)),
                     ("bypoint", GroupKFold(5))):
        pred = cross_val_predict(clf, X_lab, y, cv=cv, groups=groups, n_jobs=1)
        out[name] = {
            "acc": float(accuracy_score(y, pred)),
            "f1": float(f1_score(y, pred, average="macro")),
            "conf": confusion_matrix(y, pred).tolist(),
        }
        print("%-8s acc %.3f  macro-F1 %.3f" % (name, out[name]["acc"], out[name]["f1"]))
        print("        混淆矩阵（行=真，列=预测，易/中/难）：", out[name]["conf"])
    proba = cross_val_predict(clf, X_lab, y,
                              cv=StratifiedKFold(5, shuffle=True, random_state=0),
                              method="predict_proba", n_jobs=1)
    pred, conf = proba.argmax(1), proba.max(1)
    print("\n置信度分档（随机折）：")
    for th in (0.5, 0.6, 0.7, 0.8):
        m = conf >= th
        print("  ≥%.1f  %4d 道  准确率 %.3f  覆盖 %.0f%%"
              % (th, int(m.sum()), accuracy_score(y[m], pred[m]), 100 * m.mean()))
    clf.fit(X_lab, y)
    return clf, out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--min-conf", type=float, default=0.6)
    ap.add_argument("--min-acc", type=float, default=0.68)
    a = ap.parse_args()

    sig = store.volume_signature()          # 训练几分钟，写回前要确认库没被改
    qs, lab, X_lab, X_all, y, groups = build()
    print("全库 %d 道；人工难度 %d 道 %s\n"
          % (len(qs), len(lab), dict(Counter(q.meta["difficulty"] for q in lab))))
    clf, cv = train_and_report(lab, X_lab, y, groups)
    if cv["random"]["acc"] < a.min_acc:
        print("\n随机折准确率 %.3f < 阈值 %.2f，**不写回**。"
              % (cv["random"]["acc"], a.min_acc))
        return 1

    proba = clf.predict_proba(X_all)
    pred, conf = proba.argmax(1), proba.max(1)
    own = [q.meta.get("difficulty") in LABELS for q in qs]
    todo = [i for i, q in enumerate(qs) if not own[i]]
    hi = [i for i in todo if conf[i] >= a.min_conf]
    print("\n无题目级难度 %d 道；置信 ≥%.2f 可写 %d 道（%.0f%%）；其余继续按考点派生。"
          % (len(todo), a.min_conf, len(hi), 100 * len(hi) / max(1, len(todo))))
    print("预测分布（高置信）：", dict(Counter(LABELS[pred[i]] for i in hi)))

    if not a.apply:
        print("\n干跑结束；加 --apply 写回。")
        return 0

    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    before = Counter(q.content_hash() for q in qs)
    changed = 0
    for i in hi:
        q = qs[i]
        q.meta["difficulty"] = LABELS[pred[i]]
        q.meta["difficulty_source"] = "model"
        q.meta["difficulty_conf"] = round(float(conf[i]), 3)
        changed += 1
    # 只补 meta，正文必须一个字节都不动
    print("\n将写回 %d 道（只改 meta）" % changed)
    after = Counter(q.content_hash() for q in qs)
    assert before == after, "内容指纹变了，停止"
    try:
        rep = store.rewrite_all(qs, based_on=sig)
    except store.ConcurrentWrite:
        raise SystemExit("训练期间库被别的进程写过；请重跑一次（不会覆盖别人的改动）")
    print("已写回：%d 卷 / %d 道" % (rep["volumes"], rep["count"]))

    out = ROOT / "变更记录" / ("%s_难度模型.md"
                              % _dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    out.write_text(
        "# 题目级难度模型 v1\n\n- 时间：%s\n- 人工标签：%d 道\n"
        "- 随机折准确率：%.3f；按考点折：%.3f\n- 写回：%d 道（置信 ≥ %.2f）\n"
        "- 预测分布：%s\n"
        % (stamp, len(lab), cv["random"]["acc"], cv["bypoint"]["acc"],
           changed, a.min_conf, dict(Counter(LABELS[pred[i]] for i in hi))),
        encoding="utf-8")
    print("变更记录：" + str(out.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
