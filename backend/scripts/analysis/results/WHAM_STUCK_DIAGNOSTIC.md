# WHAM stuck job diagnostic (report only — no fixes attempted)
# Job: 92d6ef380b10484f8da93f08f6816903 — status stuck at "running" since 2026-08-25
# Budget: ~30 min. Date: 2026-09-22

## Verdict

Most likely **orphaned daemon thread after process exit/reload**, not missing
weights. Secondary observation: **WHAM was never verified end-to-end** in this
repo (no completed `*_mesh.json` in outputs, git, or fixtures). Cause of any
original hang (if the thread was still alive on Aug 25) is **unclear without
historical logs** — do not treat as a recent regression from code alone.

## 1. Worker / process logs

- Mesh jobs log only via `logging` in `mesh_jobs._run_mesh_job`
  (`logger.info` / `logger.exception`) — **no dedicated per-job log file**.
- Errors that *do* complete the `except` path write `error` + truncated
  `traceback` into `*_mesh.status.json`. The stuck job has `"error": null`
  and `"status": "running"`, so that path never ran.
- Current uvicorn terminal (started 2026-09-21) has **no** `Mesh job …`
  lines for 92d6 (job is from Aug 25). Historical server stdout is gone.
- `outputs/*_wham_work/` dirs exist but are **empty** (no `wham_results.pth`).

## 2. Model weights / checkpoints

Configured `MESH_WHAM_ROOT=…/vendor/WHAM`. `WhamBackend.is_available()` →
**True**. On disk and present:

- `checkpoints/wham_vit_bedlam_w_3dpw.pth.tar` (~527 MB)
- `checkpoints/hmr2a.ckpt` (~2.7 GB)
- `dataset/body_models/smpl/SMPL_NEUTRAL.pkl`
- `dataset/body_models/J_regressor_wham.npy`
- `wham_api.py`

**Weights are not the obvious blocker** for this stuck status file.

## 3. Invocation / failure mode (code path)

From `backend/app/services/mesh_jobs.py`:

- Jobs run in `threading.Thread(..., daemon=True)`.
- Status sequence: `pending` → `running` → `done` | `error`.
- `finally` deletes `*_mesh_source*` only when the thread finishes.

Observed for 92d6:

- Status frozen at `running` (mtime **Aug 25 22:15**).
- `*_mesh_source.mp4` **still present** → `finally` never executed.
- Empty `*_mesh_source_wham_work/` → recovery never wrote results.

That pattern matches **process death / uvicorn `--reload` worker restart /
manual kill** while a daemon mesh thread was mid-flight: the daemon dies with
the process, status is never updated to `error`, and the file looks “stuck”
forever. It is also consistent with a **true hang** that never returned
(CPU WHAM can run for a long time); without Aug 25 logs we cannot tell which.

No silent `except: pass` around the main recover path — failures that raise
should become `status=error`. The stuck `running` state specifically means
the thread did not exit the `try`/`except`/`finally` normally.

## 4. Has any WHAM job ever completed?

- **outputs/**: zero `*_mesh.json`, zero `*_mesh.mp4`; one stuck
  `*_mesh.status.json`.
- **git**: mesh code is tracked; **no** committed completed mesh artifacts.
- **tests/test_mesh.py**: unit tests mock `_parse_wham_results` / types /
  backend selection — **no fixture of a real completed mesh run**, no CI
  artifact proving E2E WHAM success.

Conclusion: WHAM is **integrated and weight-bootstrapped**, but **not shown
to have completed end-to-end** in this workspace’s history. That weakens any
“it used to work and recently broke” story.

## Recommendation (diagnostic only)

- Treat 92d6 status as **stale / orphaned**, not an active worker.
- Deeper investigation (out of budget): run one short clip synchronously
  with logging to a file, or add non-daemon + heartbeat status — **not done
  here**.
- Unblock angle validation via MediaPipe (Task 2), independent of WHAM.
