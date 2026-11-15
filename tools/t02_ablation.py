"""T02 ablation of the frozen PoC on the DEV split (analysis only — the frozen params are not changed).

    python -m tools.t02_ablation --out-json reports/ablation_dev.json

Each variant starts from the frozen `params:` in configs/lab.yaml and switches off one component by overriding
its parameters (src/pipeline.py::process reads every threshold through ctx.param):

    no_blur          blur thresholds -> -1e9   (blur probability ~ 0)
    no_dark          dark pivots     -> -1e9   (dark probability ~ 0)
    no_glare         glare pivots    -> +1e9   (glare probability ~ 0)
    no_compression   blockiness pivot -> +1e9  (compression probability ~ 0)
    no_camera_ctx    cam_B uses the cam_A blur threshold
    no_night_glare   night glare pivot = day pivot

Ranking follows src/pipeline.py::run (score descending), scored with tools.t02_self_eval on reports/gold_set_dev.csv.
The eval split is never scored here.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

from src import pipeline
from src.common.context import RunContext
from src.common.io import deep_merge, load_config, set_seed
from src.common.review import AuditLog
from tools.t02_self_eval import DEFAULT_LABELS, evaluate, load_labels

OFF = 1e9
VARIANTS: dict[str, dict] = {
    "full_poc": {},
    "no_blur": {"blur_t_cam_a": -OFF, "blur_t_cam_b": -OFF},
    "no_dark": {"dark_mean_day": -OFF, "dark_mean_night": -OFF},
    "no_glare": {"glare_sat_day": OFF, "glare_sat_night": OFF},
    "no_compression": {"comp_center": OFF},
    "no_camera_ctx": {"blur_t_cam_b": None},      # filled with blur_t_cam_a below
    "no_night_glare": {"glare_sat_night": None},  # filled with glare_sat_day below
}


def rank_variant(cfg: dict, override: dict, out_dir: Path) -> pd.DataFrame:
    params = dict(cfg.get("params") or {})
    if override.get("blur_t_cam_b", 0) is None:
        override = {"blur_t_cam_b": params["blur_t_cam_a"]}
    if override.get("glare_sat_night", 0) is None:
        override = {"glare_sat_night": params["glare_sat_day"]}
    c = deep_merge(cfg, {"params": override})
    ctx = RunContext(track="t02", input_dir=Path(c["input"]), output_dir=out_dir, config=c, seed=42,
                     rng=set_seed(42), run_name="ablation", offline=True, audit=AuditLog(out_dir / "audit_log.jsonl"))
    scored = pipeline.process(ctx, pipeline.load(ctx))
    return scored.sort_values("score", ascending=False).reset_index(drop=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/lab.yaml")
    ap.add_argument("--labels", default=DEFAULT_LABELS)
    ap.add_argument("--budget", type=int)
    ap.add_argument("--out-json")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    labels = load_labels(a.labels)
    budget = a.budget or max(1, round(0.5 * len(labels)))
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, override in VARIANTS.items():
            pred = rank_variant(cfg, dict(override), Path(tmp))
            r = evaluate(labels, pred, budget)
            sl = {s["slice"]: s for s in r["slices"]}
            rows.append({
                "variant": name,
                "Defect Recall@B": r["Defect Recall@B"],
                "recall_num_den": r["recall_num_den"],
                "recall_wilson95": r["recall_wilson95"],
                "dev_flagged_recapture": r["n_flagged_recapture"],
                "clean_flagged_recapture": sum(s["clean_flagged_recapture"] or 0 for k, s in sl.items() if k.startswith("light=")),
                **{f"recall_{t}": sl.get(f"defect={t}", {}).get("recall_in_topB") for t in ["blur", "dark", "glare", "compression"]},
                "fa_topB_night": sl.get("light=night", {}).get("false_alarm_in_topB"),
                "fa_topB_cam_B": sl.get("camera_id=cam_B", {}).get("false_alarm_in_topB"),
            })
    df = pd.DataFrame(rows)
    print(df.drop(columns=["recall_wilson95"]).to_string(index=False))
    if a.out_json:
        Path(a.out_json).write_text(json.dumps({"labels": a.labels, "B": budget, "N": int(len(labels)),
                                                "variants": rows}, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
        print(f"wrote {a.out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
