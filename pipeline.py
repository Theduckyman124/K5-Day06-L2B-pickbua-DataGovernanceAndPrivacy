"""YOUR PoC PIPELINE — this is the file your group owns.

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load      input + provenance check (manifest.csv)
    02 process   your algorithm / model (the research part)
    03 rank      prioritise for a fixed review budget B
    04 review    human-in-the-loop: queue -> reviewer decisions -> overrides + audit log
    05 decide    GO / HOLD / REWORK (or track equivalent) with reason_code + owner, write outputs

Required output: out/<pred_file> with the columns listed for your track in
docs/tracks/TXX.md (also in src/metrics/tracks.py::TRACKS). Then evaluate with
    python -m src.evaluate --track tXX --pred out/<pred_file>

Rules: never read fixtures/*/gt/ here (the GT guard will stop you); seed everything via ctx.rng;
no network calls; fail loudly on missing models instead of downloading.
See src/examples/random_baseline.py for a minimal end-to-end wiring example.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.image_ops import brightness_stats, laplacian_variance, load_rgb, to_gray
from .common.manifest import verify_manifest
from .common.review import apply_overrides, load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    data = {"manifest": pd.read_csv(manifest) if manifest.exists() else None}
    images_path = ctx.input_dir / "images.csv"
    if images_path.exists():
        data["images"] = pd.read_csv(images_path)
    return data


# ---------------------------------------------------------------- 02 process
def _detect_image_defects(img_path: Path, camera_id: str, light: str) -> dict:
    img = load_rgb(img_path)
    gray = to_gray(img)
    H, W = gray.shape

    # 1. Blur detection (Laplacian variance normalized by camera/light)
    lap_var = laplacian_variance(img)
    ref_var = 800.0 if camera_id == "cam_A" else 400.0
    if light == "night":
        ref_var *= 1.5

    if lap_var < 20.0:
        s_blur = 1.0
    elif lap_var < 80.0:
        s_blur = 0.85
    elif lap_var < ref_var * 0.35:
        s_blur = 0.70
    elif lap_var < ref_var * 0.55:
        s_blur = 0.50
    else:
        s_blur = 0.0

    # 2. Dark detection (relative to light condition)
    b = brightness_stats(img)
    mean_val = b["mean"]
    frac_dark = b["frac_dark"]
    if light == "night":
        if mean_val < 10.0 or frac_dark > 0.90:
            s_dark = 0.95
        elif mean_val < 20.0 or frac_dark > 0.80:
            s_dark = 0.65
        else:
            s_dark = 0.0
    elif light == "dusk":
        if mean_val < 30.0 or frac_dark > 0.60:
            s_dark = 0.95
        elif mean_val < 50.0 or frac_dark > 0.30:
            s_dark = 0.70
        else:
            s_dark = 0.0
    else:  # day
        if mean_val < 40.0 or frac_dark > 0.50:
            s_dark = 0.95
        elif mean_val < 65.0 or frac_dark > 0.25:
            s_dark = 0.70
        else:
            s_dark = 0.0

    # 3. Glare detection (patch-based saturation and washed-out regions)
    frac_sat = b["frac_saturated"]
    patch_sats = []
    patch_means = []
    for r in range(4):
        for c in range(4):
            patch = gray[r * H // 4 : (r + 1) * H // 4, c * W // 4 : (c + 1) * W // 4]
            patch_sats.append((patch > 240).mean())
            patch_means.append(patch.mean())
    max_patch_sat = max(patch_sats)
    max_patch_mean = max(patch_means)

    if light == "night" and mean_val > 55.0:
        s_glare = 0.95
    elif max_patch_sat > 0.08 or frac_sat > 0.03:
        s_glare = 0.90
    elif max_patch_sat > 0.04 or frac_sat > 0.015:
        s_glare = 0.70
    elif max_patch_mean > 235:
        s_glare = 0.60
    else:
        s_glare = 0.0

    # 4. Compression detection (blockiness at 8x8 boundaries)
    diff_h = np.abs(gray[:, 1:] - gray[:, :-1])
    cols = np.arange(7, W - 1, 8)
    grid_diff = diff_h[:, cols].mean() if len(cols) > 0 else 0
    non_grid_cols = [c for c in range(W - 1) if (c + 1) % 8 != 0]
    non_grid_diff = diff_h[:, non_grid_cols].mean() if len(non_grid_cols) > 0 else 1e-5
    blockiness = grid_diff / max(non_grid_diff, 1e-5)

    if blockiness > 2.5:
        s_comp = 0.90
    elif blockiness > 1.8:
        s_comp = 0.70
    elif blockiness > 1.4:
        s_comp = 0.45
    else:
        s_comp = 0.0

    scores = {
        "blur": s_blur,
        "dark": s_dark,
        "glare": s_glare,
        "compression": s_comp,
    }
    best_defect = max(scores, key=scores.get)
    max_score = scores[best_defect]

    continuous_bonus = 0.0
    if best_defect == "blur":
        continuous_bonus = 0.05 / (1.0 + lap_var / 10.0)
    elif best_defect == "dark":
        continuous_bonus = 0.05 * (1.0 - mean_val / 100.0)
    elif best_defect == "glare":
        continuous_bonus = 0.05 * min(1.0, max_patch_sat * 10)
    elif best_defect == "compression":
        continuous_bonus = 0.05 * min(1.0, (blockiness - 1.0) / 2.0)

    final_score = round(float(max_score + continuous_bonus), 4)
    pred_type = best_defect if max_score >= 0.45 else "none"
    pred_action = "RECAPTURE" if max_score >= 0.45 else "KEEP"

    return {
        "score": final_score,
        "pred_defect_type": pred_type,
        "pred_action": pred_action,
    }


def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    spec = get_track(ctx.track)
    if ctx.track != "t02":
        raise NotImplementedError(
            f"Implement process() for {spec.track} ({spec.title}). It must produce a DataFrame with at least "
            f"{spec.pred_columns} (saved as out/{spec.pred_file}). See docs/tracks/{spec.track.upper()}.md"
        )

    images = data.get("images")
    if images is None or "image_id" not in images.columns:
        raise ValueError("T02 requires images.csv with 'image_id'")

    rows = []
    for _, item in images.iterrows():
        img_p = ctx.input_dir / item["path"]
        cam = str(item.get("camera_id", "cam_A"))
        light = str(item.get("light", "day"))
        defect_info = _detect_image_defects(img_p, cam, light)
        rows.append({
            "image_id": item["image_id"],
            "score": defect_info["score"],
            "pred_defect_type": defect_info["pred_defect_type"],
            "pred_action": defect_info["pred_action"],
            "path": item["path"],
            "camera_id": cam,
            "light": light,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    budget = int(ctx.param("budget", 20))
    if "score" not in scored.columns:
        raise ValueError("rank(): process() output needs a numeric `score` column")
    evidence = "path" if "path" in scored.columns else None
    reason = "pred_defect_type" if "pred_defect_type" in scored.columns else None
    action = "pred_action" if "pred_action" in scored.columns else None
    q = make_review_queue(
        scored,
        id_col="image_id",
        score_col="score",
        budget=budget,
        reason_col=reason,
        action_col=action,
        slice_col="light" if "light" in scored.columns else None,
        evidence_col=evidence,
    )
    write_review_queue(q, ctx.out("review_queue.csv"))
    if evidence:
        render_contact_sheet(
            q,
            ctx.out("contact_sheet.html"),
            image_root=ctx.input_dir,
            title=f"T02 QC Triage Review Queue (Top {budget})",
        )
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)
        out = apply_overrides(scored, reviewed, id_col="image_id", value_col="pred_action", audit=ctx.audit)
        return out
    return scored


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    owner = ctx.config.get("owner", "Hung Vu (QA Lead)")
    n_total = len(final)
    n_recapture = int((final["pred_action"] == "RECAPTURE").sum()) if "pred_action" in final.columns else 0
    recapture_rate = n_recapture / max(n_total, 1)

    ctx.stats["n_recapture"] = n_recapture
    ctx.stats["recapture_rate"] = round(recapture_rate, 4)

    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    has_review = reviewed_path.exists() and ctx.stats.get("n_reviewed", 0) > 0

    if recapture_rate > 0.20:
        status = "HOLD" if not has_review else "REWORK"
        reason_code = "HIGH_DEFECT_RATE_HOLD" if not has_review else "RECAPTURE_REQUIRED"
        reason = (
            f"High defect rate ({n_recapture}/{n_total} = {recapture_rate:.1%}); "
            f"{'pending human sign-off on review queue' if not has_review else 'triage confirmed defective images require recapture'}"
        )
    else:
        status = "GO"
        reason_code = "DEFECT_RATE_ACCEPTABLE"
        reason = f"Defect rate ({recapture_rate:.1%}) within acceptable operating tolerance"

    return Decision(
        status=status,
        reason_code=reason_code,
        reason=reason,
        owner=owner,
        scope=ctx.track,
        evidence=[
            str(ctx.out("ranked_review.csv")),
            str(ctx.out("review_queue.csv")),
        ],
        metrics={"n_total": n_total, "n_recapture": n_recapture, "recapture_rate": round(recapture_rate, 4)},
    )


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    if "score" in final.columns:
        final = final.sort_values("score", ascending=False)
    cols = spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]
    final[cols].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
