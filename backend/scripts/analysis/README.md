# One-off analysis scripts

Standalone investigations that must **not** modify production pipeline code
(`backend/app/processing`, `schemas`, `services`).

Analysis-only Python deps (e.g. MediaPipe) live in `requirements-analysis.txt`
— install into the backend venv when needed; do **not** add them to the main
backend dependency file.

```bash
cd backend
source .venv/bin/activate
pip install -r scripts/analysis/requirements-analysis.txt

# WHAM vs 2D (blocked until joints_3d exist)
python scripts/analysis/wham_vs_2d_angles.py --outputs ../outputs

# MediaPipe world-3D vs 2D (primary validation path)
python scripts/analysis/mediapipe_vs_2d_angles.py --outputs ../outputs
```

Results land under `scripts/analysis/results/`.
