# WHAM vs 2D angles — Step 1 report

## Verdict
**BLOCKED — do not run Step 2 comparisons yet.**

## 1. Data availability
- RTMPose-complete clips (pose + smoothed + angles): **21**
- `*_mesh.status.json`: ['92d6ef380b10484f8da93f08f6816903']
- `*_mesh.json`: (none)
- Clips with usable `joints_3d`: (none)
- Camera-angle metadata present: **False**

## 2. Frame correspondence
- Design/self-check OK: **True**
  - WHAM MeshFrame.frame_index is set from WHAM payload frame_ids (fallback: arange(T)); align.py looks up pose via pose_by[mesh_frame.frame_index] — design intent is shared source-video frame indices, not timestamps.
  - MeshSequence.save_summary_json currently OMITs joints_3d, so completed mesh jobs do not leave comparable 3D joints on disk without a separate cache.
  - 158b00e1b4dd4426ae7d904d1ea568ba: RTMPose raw/smoothed/angles share identical frame_index sequence length=97 range=0..96
  - 3670048772924aeb96ece19283e64f9c: RTMPose raw/smoothed/angles share identical frame_index sequence length=286 range=0..285
  - 42e19ff79c724b31b18b66a4917166e8: RTMPose raw/smoothed/angles share identical frame_index sequence length=286 range=0..285
  - 4ae625ee39a447058d45fbe986462890: RTMPose raw/smoothed/angles share identical frame_index sequence length=184 range=0..183
  - 5d562c02eb0845d48d93667c3c88cc8d: RTMPose raw/smoothed/angles share identical frame_index sequence length=184 range=0..183
  - No joints_3d artifacts found — cannot empirically confirm WHAM frame_ids match RTMPose for any clip (design is sound; data missing).
  - No filming-angle / camera-view metadata found on evidence, overlay_meta, or dataset artifacts — cannot stratify divergence by camera angle.

## 3. SMPL joint mapping
- Resolved: **True**
  - OK left_shoulder → SMPL index 16
  - OK right_shoulder → SMPL index 17
  - OK left_elbow → SMPL index 18
  - OK right_elbow → SMPL index 19
  - OK left_hip → SMPL index 1
  - OK right_hip → SMPL index 2
  - Required joint pelvis → 0
  - Required joint right_ankle → 8
  - Required joint right_elbow → 19
  - Required joint right_hip → 2
  - Required joint right_knee → 5
  - Required joint right_shoulder → 17
  - Required joint right_wrist → 21
  - left/right shoulder distinct (16 vs 17)
  - left/right elbow distinct (18 vs 19)
  - left/right hip distinct (1 vs 2)
  - left/right knee distinct (4 vs 5)
  - Triplet OK right_elbow: right_shoulder–right_elbow–right_wrist
  - Triplet OK right_knee: right_hip–right_knee–right_ankle
  - Triplet OK right_shoulder: right_hip–right_shoulder–right_elbow
  - Triplet OK right_hip: right_shoulder–right_hip–right_knee

## 4. Angle formula
- 2D path: import `app.processing.angles.compute_angle_sequence` / `angle_at_vertex`.
- 3D path: `angle_at_vertex_3d` in this script — same acos(dot/norms) interior angle,
  applied to root-centered SMPL joint XYZ (pelvis subtracted).

## Blockers
- DATA: No clip has persisted WHAM joints_3d. Found 21 RTMPose-complete clips, 0 *_mesh.json, 1 mesh.status files, 0 mesh.mp4. save_summary_json omits joints_3d; all wham_work dirs are empty; the only mesh.status observed was stuck at status=running. Step 2 cannot run without regenerating WHAM (--run-wham) or providing {id}_mesh_joints.npz under the results cache.

## Recommendation (pre-Step-2)
- Joint map and formula are resolvable from code.
- Frame alignment is designed around shared `frame_index`; RTMPose artifacts are
  self-consistent. Empirical WHAM↔RTMPose overlap is unproven until joints exist.
- **Do not approximate** missing WHAM joints or invent an offset — regenerate WHAM
  into `results/{id}_mesh_joints.npz` via `--run-wham`, or persist joints_3d from
  a completed mesh job into that cache format, then re-run with `--run-step2`.
