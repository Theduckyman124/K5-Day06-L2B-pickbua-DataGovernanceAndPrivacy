"""T02 self-evaluation on the DEV split with the group's own gold set (not the official eval).

    python -m tools.t02_self_eval --pred out/poc/ranked_review.csv --run-name poc --out reports/selfeval_dev_poc.json

Same definitions as src/metrics/tracks.py::eval_t02, restricted to the 56 dev images:
    Defect Recall@B = defects (gold) in top-B / defects
    Precision@B     = defects (gold) in top-B / B
    False alarm in top-B per slice = clean images in top-B / clean images of that slice
Default B = 50% of the dev images (same ratio as eval: 20 of 40) -> B = 28. Wilson 95% CI because N is small.
Ranking: score descending, stable (mergesort) on the order of the prediction file.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

from src.metrics.ranking import precision_at_k, recall_at_k

DEFAULT_LABELS = "reports/gold_set_dev.csv"


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def evaluate(labels: pd.DataFrame, pred: pd.DataFrame, budget: int) -> dict:
    labels = labels.copy()
    labels["is_defect"] = labels["is_defect"].astype(int)
    pred = pred[pred["image_id"].isin(labels["image_id"])].sort_values("score", ascending=False, kind="mergesort")
    pos = labels.loc[labels["is_defect"] == 1, "image_id"]
    r = recall_at_k(pred["image_id"], pos, budget)
    p = precision_at_k(pred["image_id"], pos, budget)
    top = set(pred["image_id"].head(budget))
    flagged = set(pred.loc[pred["pred_action"] == "RECAPTURE", "image_id"]) if "pred_action" in pred.columns else set()
    res = {
        "N": int(len(labels)), "B": int(budget), "n_defects": int(len(pos)),
        "Defect Recall@B": r["value"], "recall_num_den": [r["numerator"], r["denominator"]],
        "recall_wilson95": wilson(r["numerator"], r["denominator"]),
        "Precision@B": p["value"], "precision_num_den": [p["numerator"], p["denominator"]],
        "precision_wilson95": wilson(p["numerator"], p["denominator"]),
        "n_flagged_recapture": int(len(flagged)),
        "slices": [],
    }
    for key in ["light", "camera_id"]:
        for s, sub in labels.groupby(key):
            neg, posn = sub[sub.is_defect == 0], sub[sub.is_defect == 1]
            res["slices"].append({
                "slice": f"{key}={s}", "n": int(len(sub)),
                "recall_in_topB": round(posn.image_id.isin(top).sum() / len(posn), 4) if len(posn) else None,
                "false_alarm_in_topB": round(neg.image_id.isin(top).sum() / len(neg), 4) if len(neg) else None,
                "clean_flagged_recapture": int(neg.image_id.isin(flagged).sum()),
            })
    for t, sub in labels[labels.is_defect == 1].groupby("defect_type"):
        res["slices"].append({"slice": f"defect={t}", "n": int(len(sub)),
                              "recall_in_topB": round(sub.image_id.isin(top).sum() / len(sub), 4),
                              "false_alarm_in_topB": None, "clean_flagged_recapture": None})
    if "pred_defect_type" in pred.columns and len(pos):
        m = labels[labels.is_defect == 1].merge(pred[["image_id", "pred_defect_type"]], on="image_id", how="left")
        res["defect_type_accuracy_on_defects"] = round(float((m.defect_type == m.pred_defect_type).mean()), 4)
    return res


def load_labels(path: str | Path) -> pd.DataFrame:
    labels = pd.read_csv(path)
    if "split" in labels.columns and (labels["split"] != "dev").any():
        raise SystemExit("labels contain non-dev images: self-evaluation must stay on the dev split")
    return labels


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", default=DEFAULT_LABELS)
    ap.add_argument("--pred", required=True, help="ranked_review.csv written by src.main")
    ap.add_argument("--budget", type=int, help="default = round(0.5 * N_dev)")
    ap.add_argument("--run-name", default="")
    ap.add_argument("--out", help="write JSON, e.g. reports/selfeval_dev_poc.json")
    a = ap.parse_args(argv)
    labels = load_labels(a.labels)
    pred = pd.read_csv(a.pred)
    budget = a.budget or max(1, round(0.5 * len(labels)))
    res = {"run_name": a.run_name, "labels": a.labels, "pred": a.pred} | evaluate(labels, pred, budget)
    print(json.dumps({k: v for k, v in res.items() if k != "slices"}, ensure_ascii=False, indent=2))
    print(pd.DataFrame(res["slices"]).to_string(index=False))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
