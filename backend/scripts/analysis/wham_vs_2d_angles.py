#!/usr/bin/env python3
"""Compare root-centered WHAM 3D joint angles vs RTMPose 2D angles.

Standalone investigation — does not modify processing/schemas/services.

Default mode runs Step-1 probes only and exits non-zero if any blocker remains
(missing joints_3d artifacts, unresolved frame alignment, unresolved joint map).

When `{analysis_id}_mesh_joints.npz` (or compatible JSON) exists under --outputs
or --cache-dir, Step 2 computes MAD / max |Δ| and frame-to-frame jitter, and
optionally writes an overlay plot for one clip.

Usage (from backend/):
  python scripts/analysis/wham_vs_2d_angles.py --outputs ../outputs
  python scripts/analysis/wham_vs_2d_angles.py --outputs ../outputs --run-step2
  python scripts/analysis/wham_vs_2d_angles.py --outputs ../outputs --run-wham \\
      --analysis-id 92d6ef380b10484f8da93f08f6816903
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

# Allow `python scripts/analysis/...` from repo root or backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.cv.mesh.align import ALIGNMENT_JOINTS  # noqa: E402
from app.cv.racket.pose_context import load_pose_sequence  # noqa: E402
from app.processing.angles import (  # noqa: E402
    _JOINT_TRIPLETS,
    angle_at_vertex,
    compute_angle_sequence,
)
from app.schemas.pose import Keypoint  # noqa: E402

# ---------------------------------------------------------------------------
# SMPL (24-joint) index map — standard SMPL body model order.
# ALIGNMENT_JOINTS in app.cv.mesh.align documents shoulders/elbows/hips;
# knees/wrists/ankles/pelvis follow the same SMPL numbering.
# ---------------------------------------------------------------------------
SMPL_JOINT_INDEX: dict[str, int] = {
    "pelvis": 0,
    "left_hip": 1,
    "right_hip": 2,
    "spine1": 3,
    "left_knee": 4,
    "right_knee": 5,
    "spine2": 6,
    "left_ankle": 7,
    "right_ankle": 8,
    "spine3": 9,
    "left_foot": 10,
    "right_foot": 11,
    "neck": 12,
    "left_collar": 13,
    "right_collar": 14,
    "head": 15,
    "left_shoulder": 16,
    "right_shoulder": 17,
    "left_elbow": 18,
    "right_elbow": 19,
    "left_wrist": 20,
    "right_wrist": 21,
    "left_hand": 22,
    "right_hand": 23,
}

ROOT_JOINT = "pelvis"

# Angle name → (proximal, vertex, distal) SMPL joint names — mirrors _JOINT_TRIPLETS.
ANGLE_SMPL_TRIPLETS: dict[str, tuple[str, str, str]] = {
    "right_elbow": ("right_shoulder", "right_elbow", "right_wrist"),
    "right_knee": ("right_hip", "right_knee", "right_ankle"),
    "right_shoulder": ("right_hip", "right_shoulder", "right_elbow"),
    "right_hip": ("right_shoulder", "right_hip", "right_knee"),
}

ANGLE_NAMES = tuple(ANGLE_SMPL_TRIPLETS.keys())


@dataclass
class Step1Findings:
    clips_with_rtmpose: list[str]
    clips_with_mesh_status: list[str]
    clips_with_mesh_json: list[str]
    clips_with_joints_3d: list[str]
    camera_angle_metadata: bool
    frame_alignment_ok: bool
    frame_alignment_notes: list[str]
    joint_map_ok: bool
    joint_map_notes: list[str]
    blockers: list[str]

    @property
    def clean(self) -> bool:
        return not self.blockers


def _repo_outputs_default() -> Path:
    return _BACKEND_ROOT.parent / "outputs"


def _results_dir() -> Path:
    d = Path(__file__).resolve().parent / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def discover_rtmpose_clips(outputs: Path) -> list[str]:
    """Clips that have both raw pose and post-smoothing angle artifacts."""
    raw = {p.name.replace("_pose.json", "") for p in outputs.glob("*_pose.json")}
    angles = {
        p.name.replace("_pose_angles.json", "")
        for p in outputs.glob("*_pose_angles.json")
    }
    smoothed = {
        p.name.replace("_pose_smoothed.json", "")
        for p in outputs.glob("*_pose_smoothed.json")
    }
    return sorted(raw & angles & smoothed)


def joints_cache_path(cache_dir: Path, analysis_id: str) -> Path:
    return cache_dir / f"{analysis_id}_mesh_joints.npz"


def load_joints_3d_artifact(
    outputs: Path, cache_dir: Path, analysis_id: str
) -> dict[str, Any] | None:
    """Load per-frame joints_3d if previously persisted by this script or pipeline.

    Accepted formats
    ----------------
    - `{id}_mesh_joints.npz` with arrays frame_index (N,), joints_3d (N, J, 3)
    - `{id}_mesh.json` with frames[].joints_3d (not written by current
      MeshSequence.save_summary_json — future / manual dumps only)
    """
    npz = joints_cache_path(cache_dir, analysis_id)
    if npz.exists():
        data = np.load(npz)
        return {
            "source": str(npz),
            "frame_index": data["frame_index"].astype(np.int64),
            "joints_3d": data["joints_3d"].astype(np.float64),
            "backend": str(data["backend"]) if "backend" in data.files else "unknown",
        }

    mesh_json = outputs / f"{analysis_id}_mesh.json"
    if mesh_json.exists():
        payload = _load_json(mesh_json)
        frames = payload.get("frames") or []
        idxs: list[int] = []
        joints: list[np.ndarray] = []
        for fr in frames:
            j = fr.get("joints_3d")
            if j is None:
                continue
            idxs.append(int(fr["frame_index"]))
            joints.append(np.asarray(j, dtype=np.float64))
        if joints:
            return {
                "source": str(mesh_json),
                "frame_index": np.asarray(idxs, dtype=np.int64),
                "joints_3d": np.stack(joints, axis=0),
                "backend": str(payload.get("backend", "unknown")),
            }
    return None


def save_joints_3d_cache(
    cache_dir: Path,
    analysis_id: str,
    frame_index: np.ndarray,
    joints_3d: np.ndarray,
    *,
    backend: str,
) -> Path:
    path = joints_cache_path(cache_dir, analysis_id)
    np.savez_compressed(
        path,
        frame_index=np.asarray(frame_index, dtype=np.int64),
        joints_3d=np.asarray(joints_3d, dtype=np.float64),
        backend=np.asarray(backend),
    )
    return path


def verify_joint_map() -> tuple[bool, list[str]]:
    notes: list[str] = []
    ok = True

    # Cross-check ALIGNMENT_JOINTS against our SMPL map (code-grounded).
    for idx, name in ALIGNMENT_JOINTS.items():
        expected = SMPL_JOINT_INDEX.get(name)
        if expected is None:
            ok = False
            notes.append(f"ALIGNMENT_JOINTS name {name!r} missing from SMPL_JOINT_INDEX")
        elif expected != idx:
            ok = False
            notes.append(
                f"Mismatch for {name}: ALIGNMENT_JOINTS={idx}, SMPL_JOINT_INDEX={expected}"
            )
        else:
            notes.append(f"OK {name} → SMPL index {idx}")

    required = {
        "right_elbow",
        "right_shoulder",
        "right_hip",
        "right_knee",
        "right_wrist",
        "right_ankle",
        "pelvis",
    }
    for name in sorted(required):
        if name not in SMPL_JOINT_INDEX:
            ok = False
            notes.append(f"Missing required joint {name}")
        else:
            notes.append(f"Required joint {name} → {SMPL_JOINT_INDEX[name]}")

    # Confirm left/right are distinct.
    for base in ("shoulder", "elbow", "hip", "knee"):
        li = SMPL_JOINT_INDEX[f"left_{base}"]
        ri = SMPL_JOINT_INDEX[f"right_{base}"]
        if li == ri:
            ok = False
            notes.append(f"left/right {base} share index {li}")
        else:
            notes.append(f"left/right {base} distinct ({li} vs {ri})")

    # Triplet consistency with angles.py
    for angle_name, proximal, vertex, distal in _JOINT_TRIPLETS:
        smpl = ANGLE_SMPL_TRIPLETS.get(angle_name)
        if smpl != (proximal, vertex, distal):
            ok = False
            notes.append(
                f"Triplet mismatch for {angle_name}: angles.py="
                f"{(proximal, vertex, distal)} script={smpl}"
            )
        else:
            notes.append(f"Triplet OK {angle_name}: {proximal}–{vertex}–{distal}")

    return ok, notes


def verify_frame_alignment_design(outputs: Path) -> tuple[bool, list[str]]:
    """Code + artifact checks for shared frame_index indexing.

    Empirical WHAM↔RTMPose overlap cannot be proven without joints_3d on disk;
    we still validate RTMPose artifact self-consistency and document the WHAM
    design contract from backends/wham.py + align.py.
    """
    notes: list[str] = []
    ok = True

    notes.append(
        "WHAM MeshFrame.frame_index is set from WHAM payload frame_ids "
        "(fallback: arange(T)); align.py looks up pose via pose_by[mesh_frame.frame_index] "
        "— design intent is shared source-video frame indices, not timestamps."
    )
    notes.append(
        "MeshSequence.save_summary_json currently OMITs joints_3d, so completed "
        "mesh jobs do not leave comparable 3D joints on disk without a separate cache."
    )

    clips = discover_rtmpose_clips(outputs)
    sample = clips[:5] if clips else []
    for aid in sample:
        raw = _load_json(outputs / f"{aid}_pose.json")
        sm = _load_json(outputs / f"{aid}_pose_smoothed.json")
        ang = _load_json(outputs / f"{aid}_pose_angles.json")
        raw_idxs = [f["frame_index"] for f in raw.get("frames", [])]
        sm_idxs = [f["frame_index"] for f in sm.get("frames", [])]
        ang_idxs = [f["frame_index"] for f in ang.get("frames", [])]
        if raw_idxs != sm_idxs or raw_idxs != ang_idxs:
            ok = False
            notes.append(
                f"{aid}: RTMPose raw/smoothed/angles frame_index lists diverge "
                f"(n={len(raw_idxs)}/{len(sm_idxs)}/{len(ang_idxs)})"
            )
        elif raw_idxs and raw_idxs != list(range(raw_idxs[0], raw_idxs[0] + len(raw_idxs))):
            notes.append(
                f"{aid}: frame_index not contiguous from {raw_idxs[0]} "
                f"(gaps present — join by frame_index, not list position)"
            )
        else:
            notes.append(
                f"{aid}: RTMPose raw/smoothed/angles share identical frame_index "
                f"sequence length={len(raw_idxs)} range="
                f"{raw_idxs[0] if raw_idxs else None}..{raw_idxs[-1] if raw_idxs else None}"
            )

    # Check any available joints artifact for index overlap.
    cache = _results_dir()
    joints_clips = []
    for aid in clips:
        art = load_joints_3d_artifact(outputs, cache, aid)
        if art is None:
            continue
        joints_clips.append(aid)
        pose_idxs = {
            f["frame_index"]
            for f in _load_json(outputs / f"{aid}_pose.json").get("frames", [])
        }
        mesh_idxs = set(int(x) for x in art["frame_index"].tolist())
        overlap = pose_idxs & mesh_idxs
        if not overlap:
            ok = False
            notes.append(
                f"{aid}: joints_3d present but ZERO overlapping frame_index with pose "
                f"(pose={len(pose_idxs)} mesh={len(mesh_idxs)}) — BLOCKER"
            )
        else:
            notes.append(
                f"{aid}: joints_3d∩pose frame_index overlap={len(overlap)} "
                f"(pose={len(pose_idxs)} mesh={len(mesh_idxs)}) source={art['source']}"
            )

    if not joints_clips:
        notes.append(
            "No joints_3d artifacts found — cannot empirically confirm WHAM frame_ids "
            "match RTMPose for any clip (design is sound; data missing)."
        )

    return ok, notes


def probe_camera_angle_metadata(outputs: Path) -> tuple[bool, list[str]]:
    notes: list[str] = []
    keys_of_interest = (
        "camera_view",
        "camera_angle",
        "filming_angle",
        "view_angle",
        "camera",
        "viewpoint",
    )
    found = False
    for pattern in ("*_pose_evidence.json", "*_overlay_meta.json", "*_dataset.json"):
        for path in list(outputs.glob(pattern))[:30]:
            data = _load_json(path)
            hits = [k for k in keys_of_interest if k in data]
            if hits:
                found = True
                notes.append(f"{path.name}: keys {hits}")
    if not found:
        notes.append(
            "No filming-angle / camera-view metadata found on evidence, overlay_meta, "
            "or dataset artifacts — cannot stratify divergence by camera angle."
        )
    return found, notes


def run_step1(outputs: Path, cache_dir: Path) -> Step1Findings:
    rtm = discover_rtmpose_clips(outputs)
    mesh_status = sorted(
        p.name.replace("_mesh.status.json", "")
        for p in outputs.glob("*_mesh.status.json")
    )
    mesh_json = sorted(
        p.name.replace("_mesh.json", "") for p in outputs.glob("*_mesh.json")
    )
    with_joints: list[str] = []
    for aid in sorted(set(rtm) | set(mesh_json) | set(mesh_status)):
        if load_joints_3d_artifact(outputs, cache_dir, aid) is not None:
            with_joints.append(aid)

    cam_ok, cam_notes = probe_camera_angle_metadata(outputs)
    align_ok, align_notes = verify_frame_alignment_design(outputs)
    joint_ok, joint_notes = verify_joint_map()

    blockers: list[str] = []
    if not with_joints:
        blockers.append(
            "DATA: No clip has persisted WHAM joints_3d. Found "
            f"{len(rtm)} RTMPose-complete clips, {len(mesh_json)} *_mesh.json, "
            f"{len(mesh_status)} mesh.status files, "
            f"{len(list(outputs.glob('*_mesh.mp4')))} mesh.mp4. "
            "save_summary_json omits joints_3d; all wham_work dirs are empty; "
            "the only mesh.status observed was stuck at status=running. "
            "Step 2 cannot run without regenerating WHAM (--run-wham) or "
            "providing {id}_mesh_joints.npz under the results cache."
        )
    if not joint_ok:
        blockers.append("JOINT MAP: unresolved — see joint_map_notes")
    # Frame alignment design is OK even without joints; only fail if we detected mismatch.
    if not align_ok:
        blockers.append("FRAME ALIGNMENT: unresolved mismatch — see frame_alignment_notes")

    findings = Step1Findings(
        clips_with_rtmpose=rtm,
        clips_with_mesh_status=mesh_status,
        clips_with_mesh_json=mesh_json,
        clips_with_joints_3d=with_joints,
        camera_angle_metadata=cam_ok,
        frame_alignment_ok=align_ok,
        frame_alignment_notes=align_notes + cam_notes,
        joint_map_ok=joint_ok,
        joint_map_notes=joint_notes,
        blockers=blockers,
    )
    return findings


def angle_at_vertex_3d(
    proximal: np.ndarray,
    vertex: np.ndarray,
    distal: np.ndarray,
) -> float:
    """Same interior-angle formula as ``angle_at_vertex`` in angles.py, in 3D.

    angles.py uses Keypoint.x/y only (image plane). Here we apply identical
    acos(dot / (|u||v|)) math to 3-vectors so differences are coordinate-space,
    not formula drift.
    """
    v_p = proximal.astype(np.float64) - vertex.astype(np.float64)
    v_d = distal.astype(np.float64) - vertex.astype(np.float64)
    norm_p = float(np.linalg.norm(v_p))
    norm_d = float(np.linalg.norm(v_d))
    if norm_p == 0.0 or norm_d == 0.0:
        raise ValueError("Degenerate joint geometry (zero-length segment)")
    cos_theta = float(np.dot(v_p, v_d) / (norm_p * norm_d))
    cos_theta = max(-1.0, min(1.0, cos_theta))
    return math.degrees(math.acos(cos_theta))


def _assert_2d_formula_parity() -> None:
    """Sanity: 3D helper with z=0 matches angles.angle_at_vertex on xy."""
    a = Keypoint(0.0, 0.0, 1.0)
    b = Keypoint(1.0, 0.0, 1.0)
    c = Keypoint(1.0, 1.0, 1.0)
    two_d = angle_at_vertex(a, b, c)
    three_d = angle_at_vertex_3d(
        np.array([a.x, a.y, 0.0]),
        np.array([b.x, b.y, 0.0]),
        np.array([c.x, c.y, 0.0]),
    )
    if abs(two_d - three_d) > 1e-9:
        raise AssertionError(f"2D/3D formula parity failed: {two_d} vs {three_d}")


def root_center(joints: np.ndarray, root_idx: int = 0) -> np.ndarray:
    return joints - joints[root_idx : root_idx + 1, :]


def angles_from_joints_3d(joints_rc: np.ndarray) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for angle_name, (prox, vert, dist) in ANGLE_SMPL_TRIPLETS.items():
        try:
            out[angle_name] = angle_at_vertex_3d(
                joints_rc[SMPL_JOINT_INDEX[prox]],
                joints_rc[SMPL_JOINT_INDEX[vert]],
                joints_rc[SMPL_JOINT_INDEX[dist]],
            )
        except (ValueError, IndexError):
            out[angle_name] = None
    return out


def load_2d_angle_series(
    outputs: Path,
    analysis_id: str,
    *,
    confidence_threshold: float = 0.5,
) -> dict[str, Any]:
    """Return raw (pre-smoothing) and post-smoothing 2D angle series by frame_index.

    Pipeline (`pose_service`) computes angles from *smoothed* pose only and writes
    `*_pose_angles.json`. Raw pre-smoothing angles are NOT persisted — we recompute
    them here from `*_pose.json` via the same ``compute_angle_sequence``.
    """
    raw_pose = load_pose_sequence(outputs / f"{analysis_id}_pose.json")
    smoothed_pose = load_pose_sequence(outputs / f"{analysis_id}_pose_smoothed.json")
    raw_angles = compute_angle_sequence(
        raw_pose, confidence_threshold=confidence_threshold
    )
    # Prefer recomputing from smoothed pose (includes right_hip if present in code)
    # over the on-disk angles artifact (older exports may omit hip).
    smoothed_recomputed = compute_angle_sequence(
        smoothed_pose, confidence_threshold=confidence_threshold
    )

    def to_maps(seq) -> dict[int, dict[str, float | None]]:
        maps: dict[int, dict[str, float | None]] = {}
        for fr in seq.frames:
            maps[fr.frame_index] = {
                "right_elbow": fr.right_elbow,
                "right_knee": fr.right_knee,
                "right_shoulder": fr.right_shoulder,
                "right_hip": fr.right_hip,
            }
        return maps

    return {
        "raw_by_frame": to_maps(raw_angles),
        "smoothed_by_frame": to_maps(smoothed_recomputed),
        "note": (
            "Pipeline discards pre-smoothing angles; raw series recomputed from "
            "*_pose.json. Smoothed series recomputed from *_pose_smoothed.json "
            "(same formula as production)."
        ),
    }


def mean_abs_frame_delta(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    diffs = [abs(values[i] - values[i - 1]) for i in range(1, len(values))]
    return float(sum(diffs) / len(diffs))


def compare_clip(
    outputs: Path,
    cache_dir: Path,
    analysis_id: str,
    *,
    confidence_threshold: float = 0.5,
) -> dict[str, Any]:
    art = load_joints_3d_artifact(outputs, cache_dir, analysis_id)
    if art is None:
        raise FileNotFoundError(f"No joints_3d for {analysis_id}")

    two_d = load_2d_angle_series(
        outputs, analysis_id, confidence_threshold=confidence_threshold
    )
    mesh_by = {
        int(fi): art["joints_3d"][i]
        for i, fi in enumerate(art["frame_index"].tolist())
    }

    per_joint: dict[str, dict[str, Any]] = {}
    for angle_name in ANGLE_NAMES:
        abs_diffs_raw: list[float] = []
        abs_diffs_sm: list[float] = []
        series_3d: list[float] = []
        series_2d_raw: list[float] = []
        series_2d_sm: list[float] = []
        frames_used: list[int] = []

        for fi in sorted(mesh_by.keys()):
            if fi not in two_d["raw_by_frame"]:
                continue
            joints = mesh_by[fi]
            if joints.ndim != 2 or joints.shape[0] < 24:
                continue
            a3 = angles_from_joints_3d(root_center(joints, SMPL_JOINT_INDEX[ROOT_JOINT]))
            v3 = a3.get(angle_name)
            v2r = two_d["raw_by_frame"][fi].get(angle_name)
            v2s = two_d["smoothed_by_frame"][fi].get(angle_name)
            if v3 is None:
                continue
            frames_used.append(fi)
            series_3d.append(v3)
            if v2r is not None:
                abs_diffs_raw.append(abs(v3 - v2r))
                series_2d_raw.append(v2r)
            if v2s is not None:
                abs_diffs_sm.append(abs(v3 - v2s))
                series_2d_sm.append(v2s)

        per_joint[angle_name] = {
            "n_frames_compared_raw": len(abs_diffs_raw),
            "n_frames_compared_smoothed": len(abs_diffs_sm),
            "mad_vs_2d_raw_deg": (
                float(sum(abs_diffs_raw) / len(abs_diffs_raw)) if abs_diffs_raw else None
            ),
            "max_abs_diff_vs_2d_raw_deg": (
                float(max(abs_diffs_raw)) if abs_diffs_raw else None
            ),
            "mad_vs_2d_smoothed_deg": (
                float(sum(abs_diffs_sm) / len(abs_diffs_sm)) if abs_diffs_sm else None
            ),
            "max_abs_diff_vs_2d_smoothed_deg": (
                float(max(abs_diffs_sm)) if abs_diffs_sm else None
            ),
            "jitter_mean_abs_delta_3d_deg": mean_abs_frame_delta(series_3d),
            "jitter_mean_abs_delta_2d_raw_deg": mean_abs_frame_delta(series_2d_raw),
            "jitter_mean_abs_delta_2d_smoothed_deg": mean_abs_frame_delta(series_2d_sm),
            "frames_used_head": frames_used[:5],
            "frames_used_tail": frames_used[-5:],
        }

    return {
        "analysis_id": analysis_id,
        "joints_source": art["source"],
        "backend": art.get("backend"),
        "mesh_frame_count": int(len(art["frame_index"])),
        "two_d_note": two_d["note"],
        "per_joint": per_joint,
        "camera_angle": None,  # no metadata in artifacts
    }


def maybe_plot_overlay(
    outputs: Path,
    cache_dir: Path,
    analysis_id: str,
    out_path: Path,
    *,
    angle_name: str = "right_elbow",
    confidence_threshold: float = 0.5,
) -> Path | None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    art = load_joints_3d_artifact(outputs, cache_dir, analysis_id)
    if art is None:
        return None
    two_d = load_2d_angle_series(
        outputs, analysis_id, confidence_threshold=confidence_threshold
    )
    xs: list[int] = []
    y3: list[float] = []
    y2r: list[float] = []
    y2s: list[float] = []
    for i, fi in enumerate(art["frame_index"].tolist()):
        fi = int(fi)
        if fi not in two_d["raw_by_frame"]:
            continue
        a3 = angles_from_joints_3d(
            root_center(art["joints_3d"][i], SMPL_JOINT_INDEX[ROOT_JOINT])
        )
        v3 = a3.get(angle_name)
        v2r = two_d["raw_by_frame"][fi].get(angle_name)
        v2s = two_d["smoothed_by_frame"][fi].get(angle_name)
        if v3 is None or v2r is None:
            continue
        xs.append(fi)
        y3.append(v3)
        y2r.append(v2r)
        y2s.append(v2s if v2s is not None else float("nan"))

    if not xs:
        return None

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(xs, y2r, label="2D raw (recomputed)", linewidth=1.0, alpha=0.85)
    ax.plot(xs, y2s, label="2D smoothed", linewidth=1.2, alpha=0.9)
    ax.plot(xs, y3, label="3D WHAM root-centered", linewidth=1.2, alpha=0.9)
    ax.set_xlabel("frame_index")
    ax.set_ylabel(f"{angle_name} (deg)")
    ax.set_title(f"{analysis_id} — {angle_name}")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path


def try_run_wham(
    outputs: Path,
    cache_dir: Path,
    analysis_id: str,
) -> Path:
    """Optional: regenerate mesh and cache joints_3d without touching pipeline files."""
    from app.cv.mesh.pipeline import recover_mesh_sequence

    video_candidates = [
        outputs / f"{analysis_id}_mesh_source.mp4",
        outputs / f"{analysis_id}_pose.mp4",
        outputs / f"{analysis_id}.mp4",
    ]
    video_path = next((p for p in video_candidates if p.exists()), None)
    if video_path is None:
        raise FileNotFoundError(
            f"No source video for {analysis_id} among {[str(p) for p in video_candidates]}"
        )

    pose_path = outputs / f"{analysis_id}_pose_smoothed.json"
    if not pose_path.exists():
        pose_path = outputs / f"{analysis_id}_pose.json"
    pose = load_pose_sequence(pose_path) if pose_path.exists() else None

    import cv2

    cap = cv2.VideoCapture(str(video_path))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if w <= 0 or h <= 0:
        raise RuntimeError(f"Could not read video size from {video_path}")

    seq = recover_mesh_sequence(
        video_path,
        pose_sequence=pose,
        image_width=w,
        image_height=h,
    )
    idxs: list[int] = []
    joints: list[np.ndarray] = []
    for fr in seq.frames:
        if fr.joints_3d is None:
            continue
        idxs.append(int(fr.frame_index))
        joints.append(np.asarray(fr.joints_3d, dtype=np.float64))
    if not joints:
        raise RuntimeError(
            "WHAM recovered frames but joints_3d is None — j_regressor missing?"
        )
    return save_joints_3d_cache(
        cache_dir,
        analysis_id,
        np.asarray(idxs, dtype=np.int64),
        np.stack(joints, axis=0),
        backend=seq.backend,
    )


def format_step1_report(findings: Step1Findings) -> str:
    lines = [
        "# WHAM vs 2D angles — Step 1 report",
        "",
        "## Verdict",
        (
            "**BLOCKED — do not run Step 2 comparisons yet.**"
            if findings.blockers
            else "**Step 1 clean — Step 2 may proceed.**"
        ),
        "",
        "## 1. Data availability",
        f"- RTMPose-complete clips (pose + smoothed + angles): **{len(findings.clips_with_rtmpose)}**",
        f"- `*_mesh.status.json`: {findings.clips_with_mesh_status or '(none)'}",
        f"- `*_mesh.json`: {findings.clips_with_mesh_json or '(none)'}",
        f"- Clips with usable `joints_3d`: {findings.clips_with_joints_3d or '(none)'}",
        f"- Camera-angle metadata present: **{findings.camera_angle_metadata}**",
        "",
        "## 2. Frame correspondence",
        f"- Design/self-check OK: **{findings.frame_alignment_ok}**",
    ]
    for n in findings.frame_alignment_notes:
        lines.append(f"  - {n}")
    lines += [
        "",
        "## 3. SMPL joint mapping",
        f"- Resolved: **{findings.joint_map_ok}**",
    ]
    for n in findings.joint_map_notes:
        lines.append(f"  - {n}")
    lines += [
        "",
        "## 4. Angle formula",
        "- 2D path: import `app.processing.angles.compute_angle_sequence` / `angle_at_vertex`.",
        "- 3D path: `angle_at_vertex_3d` in this script — same acos(dot/norms) interior angle,",
        "  applied to root-centered SMPL joint XYZ (pelvis subtracted).",
        "",
        "## Blockers",
    ]
    if findings.blockers:
        for b in findings.blockers:
            lines.append(f"- {b}")
    else:
        lines.append("- (none)")
    lines += [
        "",
        "## Recommendation (pre-Step-2)",
        "- Joint map and formula are resolvable from code.",
        "- Frame alignment is designed around shared `frame_index`; RTMPose artifacts are",
        "  self-consistent. Empirical WHAM↔RTMPose overlap is unproven until joints exist.",
        "- **Do not approximate** missing WHAM joints or invent an offset — regenerate WHAM",
        "  into `results/{id}_mesh_joints.npz` via `--run-wham`, or persist joints_3d from",
        "  a completed mesh job into that cache format, then re-run with `--run-step2`.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outputs",
        type=Path,
        default=_repo_outputs_default(),
        help="Directory containing analysis artifacts (default: repo outputs/)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Where to read/write {id}_mesh_joints.npz (default: scripts/analysis/results)",
    )
    parser.add_argument(
        "--run-step2",
        action="store_true",
        help="Run comparison if Step 1 is clean (has joints_3d)",
    )
    parser.add_argument(
        "--run-wham",
        action="store_true",
        help="Call existing recover_mesh_sequence for --analysis-id and cache joints_3d",
    )
    parser.add_argument("--analysis-id", type=str, default=None)
    parser.add_argument("--plot", action="store_true", help="Write elbow overlay plot")
    parser.add_argument("--confidence-threshold", type=float, default=0.5)
    args = parser.parse_args(argv)

    outputs = args.outputs.resolve()
    cache_dir = (args.cache_dir or _results_dir()).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    results = _results_dir()

    _assert_2d_formula_parity()

    if args.run_wham:
        if not args.analysis_id:
            print("--run-wham requires --analysis-id", file=sys.stderr)
            return 2
        print(f"Running WHAM recovery for {args.analysis_id} …")
        path = try_run_wham(outputs, cache_dir, args.analysis_id)
        print(f"Cached joints_3d → {path}")

    findings = run_step1(outputs, cache_dir)
    report = format_step1_report(findings)
    report_path = results / "wham_vs_2d_angles_STEP1_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nWrote {report_path}")

    if findings.blockers:
        print("\nSTOP: Step 1 blockers present — not running misleading Step 2 comparisons.")
        return 1

    if not args.run_step2:
        print("\nStep 1 clean. Re-run with --run-step2 to compute comparisons.")
        return 0

    clip_ids = findings.clips_with_joints_3d
    if args.analysis_id:
        clip_ids = [args.analysis_id]

    summaries: list[dict[str, Any]] = []
    for aid in clip_ids:
        print(f"\n=== Comparing {aid} ===")
        summary = compare_clip(
            outputs,
            cache_dir,
            aid,
            confidence_threshold=args.confidence_threshold,
        )
        summaries.append(summary)
        print(json.dumps(summary, indent=2))
        if args.plot:
            plot_path = results / f"{aid}_right_elbow_overlay.png"
            written = maybe_plot_overlay(
                outputs,
                cache_dir,
                aid,
                plot_path,
                confidence_threshold=args.confidence_threshold,
            )
            print(f"Plot: {written}")

    out_json = results / "wham_vs_2d_angles_STEP2_SUMMARY.json"
    out_json.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(f"\nWrote {out_json}")

    # Short overall recommendation stub when we have numbers.
    rec_path = results / "wham_vs_2d_angles_RECOMMENDATION.md"
    rec_lines = [
        "# WHAM vs 2D — Step 2 summary",
        "",
        f"Clips compared: {len(summaries)}",
        "",
        "See `wham_vs_2d_angles_STEP2_SUMMARY.json` for per-joint MAD / max / jitter.",
        "",
        "Interpretation checklist:",
        "- Large 2D↔3D MAD that grows with more oblique filming → supports camera-distortion",
        "  hypothesis (favor pursuing 3D angles).",
        "- 3D frame-to-frame jitter ≫ 2D raw jitter → WHAM too noisy for per-frame coaching",
        "  metrics (favor MediaPipe / dedicated lift, or heavy temporal smoothing).",
        "",
    ]
    for s in summaries:
        rec_lines.append(f"## {s['analysis_id']}")
        for j, stats in s["per_joint"].items():
            rec_lines.append(
                f"- {j}: MAD_raw={stats['mad_vs_2d_raw_deg']}, "
                f"MAD_sm={stats['mad_vs_2d_smoothed_deg']}, "
                f"jitter3d={stats['jitter_mean_abs_delta_3d_deg']}, "
                f"jitter2d_raw={stats['jitter_mean_abs_delta_2d_raw_deg']}"
            )
        rec_lines.append("")
    rec_path.write_text("\n".join(rec_lines), encoding="utf-8")
    print(f"Wrote {rec_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
