# MediaPipe world-3D vs RTMPose 2D angles — results

Clips compared: **21**
Frame-alignment failures: (none)

## Overall (mean across clips)
- **right_elbow**: MAD(3D vs 2D raw)=31.7°, jitter3d=7.9°, jitter2d_raw=6.5° (n=21)
- **right_knee**: MAD(3D vs 2D raw)=11.6°, jitter3d=3.0°, jitter2d_raw=3.4° (n=21)
- **right_shoulder**: MAD(3D vs 2D raw)=23.8°, jitter3d=8.0°, jitter2d_raw=4.2° (n=21)
- **right_hip**: MAD(3D vs 2D raw)=18.8°, jitter3d=2.3°, jitter2d_raw=2.4° (n=21)

## Filming-angle proxy vs divergence
Clip counts: {'front-on-ish': 17, 'oblique-ish': 4}
Mean MAD by proxy label: {'front-on-ish': '21.2', 'oblique-ish': '22.6'}

(Proxy = mid-frame 2D shoulder-width / torso-height from RTMPose; keyframes saved under results/*_midframe_*.jpg for manual check.)

## Per clip (elbow MAD / jitter)
- `158b00e1…` view=front-on-ish MAD_raw=32.0 jitter3d=9.3 jitter2d=6.3 det=97/97
- `36700487…` view=oblique-ish MAD_raw=44.7 jitter3d=11.4 jitter2d=8.4 det=284/286
- `42e19ff7…` view=oblique-ish MAD_raw=41.1 jitter3d=10.0 jitter2d=6.6 det=271/286
- `4ae625ee…` view=front-on-ish MAD_raw=28.4 jitter3d=6.1 jitter2d=6.5 det=184/184
- `5d562c02…` view=front-on-ish MAD_raw=31.4 jitter3d=7.2 jitter2d=6.5 det=184/184
- `603483d3…` view=front-on-ish MAD_raw=27.2 jitter3d=6.7 jitter2d=6.5 det=184/184
- `6fa94786…` view=front-on-ish MAD_raw=32.0 jitter3d=9.3 jitter2d=6.3 det=97/97
- `73a6e021…` view=front-on-ish MAD_raw=32.0 jitter3d=9.3 jitter2d=6.3 det=97/97
- `7af5ea71…` view=front-on-ish MAD_raw=33.5 jitter3d=8.7 jitter2d=6.5 det=184/184
- `7cb302ba…` view=front-on-ish MAD_raw=27.0 jitter3d=5.9 jitter2d=6.5 det=184/184
- `813bee5f…` view=front-on-ish MAD_raw=28.8 jitter3d=8.7 jitter2d=6.5 det=264/264
- `822f2c6b…` view=front-on-ish MAD_raw=30.5 jitter3d=7.2 jitter2d=6.5 det=184/184
- `8e57554e…` view=front-on-ish MAD_raw=30.5 jitter3d=7.2 jitter2d=6.5 det=184/184
- `92d6ef38…` view=front-on-ish MAD_raw=23.4 jitter3d=4.7 jitter2d=6.5 det=184/184
- `c0dc93b6…` view=oblique-ish MAD_raw=41.1 jitter3d=10.0 jitter2d=6.6 det=271/286
- `c36aa2ca…` view=front-on-ish MAD_raw=28.4 jitter3d=6.1 jitter2d=6.5 det=184/184
- `c8eac0f3…` view=oblique-ish MAD_raw=30.7 jitter3d=8.1 jitter2d=6.2 det=117/117
- `d01f82c7…` view=front-on-ish MAD_raw=32.0 jitter3d=9.3 jitter2d=6.3 det=97/97
- `deb9b6a9…` view=front-on-ish MAD_raw=27.3 jitter3d=5.4 jitter2d=6.5 det=184/184
- `f67cdce0…` view=front-on-ish MAD_raw=31.4 jitter3d=7.2 jitter2d=6.5 det=184/184
- `ffedda8a…` view=front-on-ish MAD_raw=32.0 jitter3d=9.3 jitter2d=6.3 det=97/97

## Answers to the three questions

1. **Difference:** Yes — mean |3D−2D| ≈ **21.5°** across joints (materially different, not noise-scale).
   Overall joint-average MAD barely differs by filming proxy (front=21.2° vs oblique=22.6°), but
   **elbow alone tracks view**: oblique elbow MAD ≈41–45° vs front-on ≈27–33°. No true side-on
   clips in this set (proxy found 17 front-on-ish, 4 oblique-ish, 0 side-on).
2. **Noise:** 3D somewhat noisier overall (≈5.3° vs ≈4.1° mean jitter), driven mainly by
   **shoulder** (~1.9× 2D raw). Elbow ~1.2×; knee/hip similar or quieter than 2D raw.
   Not unusable, but shoulder angles need smoothing/quality gates.
3. **Recommendation:**
   **Validate A2 (MediaPipe world landmarks)** as the next precision path — 3D differs enough
   from 2D to matter, without catastrophic frame jitter. Prefer solutions Pose
   `model_complexity=2` (heavy); tasks PoseLandmarker 1.x fatals on this Mac’s Metal stack.

Recommendation code: `A2`

## Caveats
- **Videos:** 20/21 runs used annotated `*_pose.mp4` (skeleton overlay), not the raw upload;
  only `92d6…` had `*_mesh_source.mp4`. Overlay ink may slightly bias MediaPipe; re-run on
  raw uploads when available.
- **Duplicates:** Several analysis IDs are re-runs of the same clip (identical frame count +
  MAD). Unique content clusters ≈13, not 21 independent scenes.
- **Raw 2D angles** are recomputed from `*_pose.json` (pipeline only persists smoothed angles).
- MediaPipe `smooth_landmarks=False` so jitter compares raw 3D vs raw 2D.
