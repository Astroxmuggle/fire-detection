# FireWatch AI — remediation report

**Date:** 2026-10-23
**Baseline:** [`PROJECT_ASSESSMENT.md`](PROJECT_ASSESSMENT.md) (pre-remediation snapshot)
**Status:** P0 and P1 complete, verified by 78 tests, a live server run and a
reproducible evaluation.

---

## 1. Measured impact

All "after" numbers were produced by the code in this repository on this machine
(Windows 11, 8-core CPU, no GPU).

| Behaviour | Before | After |
|---|---|---|
| Uniform white frame | **fire @ 0.725** → alarm | skipped by the frame guard, **0 detections** |
| Uniform light-grey frame | **fire @ 0.701** | skipped, 0 detections |
| Uniform mid-grey frame | **fire @ 0.562** | skipped, 0 detections |
| Uniform black frame | smoke @ 0.30 | skipped, 0 detections |
| Fire **and** smoke in one frame | never confirmed (`[0,0,0,0,0]`) | both confirm (`[0,2,0,…]`) |
| Fire persists after confirming | new event **every frame** (`[0,1,1,1,1]`) | **one** event, then latched (`[0,1,0,0,0]`) |
| FIRESENSE fire-negative clip | 7 raw detections → **4 confirmed false alarms** | 7 raw detections → **1 confirmed false alarm** |
| D-Fire negatives (50 images, conf 0.5) | 4 % false-positive rate | 4 % (model limit, not a pipeline bug) |
| `/incident/<id>` | **HTTP 500** (missing template fields) | 200 with evidence image |
| `/video_feed` without a camera | **HTTP 500** mid-stream | **503** JSON with a reason |
| `/api/status` camera state | hard-coded `"online"` | live runtime state |
| `/api/metrics` confirmed count | always `0` | read from the database |
| Running `pytest` | **deleted the event history** | each test uses a temporary database |
| `.env` file | never loaded | loaded (dependency-free parser) |
| Model location | absolute path outside the repo | bundled at `models/best.pt` |
| Version control | none | Git repository, initial commit |
| Test suite | 19 tests | **78 tests**, ~10 s |

### Held-out evaluation (521 images, 578 instances)

| Metric | Value |
|---|---|
| mAP@50 | **0.685** |
| mAP@50-95 | 0.328 |
| Precision / Recall | 0.712 / 0.691 |
| mAP@50 — fire | **0.937** |
| mAP@50 — smoke | **0.434** |

The class breakdown is the most useful finding for the next iteration: fire
detection is strong, smoke detection is not. That is now stated openly in the
README, the deck and the report outline instead of being hidden behind an
aggregate number.

Reproduce with:

```powershell
python evaluation/run_eval.py `
  --data evaluation\datasets\dfire-test\data.yaml `
  --negatives "C:\Users\manna_2c83x\fire-detection-ai\evaluation"
```

Reports land in [`evaluation/reports/`](evaluation/reports/).

---

## 2. What changed, file by file

### Detection pipeline

| File | Change |
|---|---|
| [`detection/confirmation.py`](detection/confirmation.py) | Rewritten. Per-class state, latch after confirmation, re-arm only after `release_frames` clear frames, optional cool-down. Adds `update_frame()` and `snapshot()`. |
| [`detection/manager.py`](detection/manager.py) | Normalises model output, applies **per-class** thresholds, NMS, min/max box-area filters, then advances confirmation once per frame. |
| [`detection/frame_guard.py`](detection/frame_guard.py) | **New.** Grayscale-variance blank-frame detection plus an overlay for skipped frames. |
| [`detection/postprocess.py`](detection/postprocess.py) | Robust bbox flattening, per-class threshold support, skips detections without a usable box. |

### Services

| File | Change |
|---|---|
| [`services/camera_service.py`](services/camera_service.py) | Rewritten around a `CameraStream` object: model + camera open **before** the response, DirectShow fallback, RTSP/file sources, single-stream lock, guaranteed release, frame-guard integration. |
| [`services/event_service.py`](services/event_service.py) | One shared `AlertManager` (cool-down now works), every confirmed event gets an alert record, filter/limit support, `get_event_stats()`. |
| [`services/status_service.py`](services/status_service.py) | **New.** Thread-safe runtime state (camera, model, frames, errors). |
| [`services/metrics_service.py`](services/metrics_service.py) | Singleton; counts derived from the database instead of a per-request object. |
| [`services/evidence_service.py`](services/evidence_service.py) | Config-driven directory, `resolve_evidence_path()` blocks path traversal. |

### Web layer

| File | Change |
|---|---|
| [`routes/web.py`](routes/web.py) | Fail-fast `/video_feed` (503/409), `/history`, incident page, `/evidence/<id>`, acknowledgement POST. |
| [`routes/api.py`](routes/api.py) | Honest `/api/status`, working `/api/metrics`, validating `PUT /api/settings`, `/api/camera/probe`, `/api/stream/stop`. |
| [`templates/`](templates/) | Rewritten: shared `base.html`, dashboard, history, incident detail, error page. The old `base.html` could not render at all. |
| [`static/css/style.css`](static/css/style.css) | Proper stylesheet for the existing markup (the dashboard previously rendered unstyled). |
| [`static/js/app.js`](static/js/app.js) | Safe DOM construction (no `innerHTML` with data), stream start/stop, error overlay, live status. |

### Configuration, tests, tooling

| File | Change |
|---|---|
| [`config.py`](config.py) | Dependency-free `.env` loader, bundled model path, per-class thresholds, frame/box guards, confirmation and logging knobs. |
| [`app.py`](app.py) | App factory, rotating file logging, HTML/JSON-aware 404/500 handlers. |
| [`conftest.py`](conftest.py) | **New.** Per-test temporary database + evidence directory; restores every mutable config value. |
| [`pytest.ini`](pytest.ini) | **New** (was only in the parent folder, which broke imports when the project moved). |
| [`tests/`](tests/) | Rewritten and expanded to 78 tests, including regression tests for every bug above. |
| [`evaluation/run_eval.py`](evaluation/run_eval.py) | **New.** Labelled metrics + negative-image scan + negative-video sequences + blank-frame probe, writes JSON and Markdown. |
| [`training/train.py`](training/train.py) | Rewritten with a CLI, a working base model, and `--copy-to-models`. |
| [`.gitignore`](.gitignore), [`.env.example`](.env.example), [`README.md`](README.md) | New/rewritten. |
| [`models/best.pt`](models/best.pt) | The 5.4 MB checkpoint now ships with the project. |
| [`assets/training/`](assets/training/) | Training curves bundled so the deck can be regenerated anywhere. |

**Removed dead code:** `database/models.py` (unused broken SQLAlchemy layer),
`detection/camera.py`, `alerts/sounds.py`, `update_deck_download.py`.

**Data hygiene:** the polluted database was archived to
`backups/fire_detection.db.20261023.bak` and recreated empty; 47 test-generated
snapshots (80×80 black frames created by the old suite) were deleted, leaving the
four genuine camera frames.

---

## 3. Presentation material

Every numeric claim was replaced with a measured value, and the claims that were
not true were rewritten:

* CPU throughput: "20–30 FPS" → **4.7 FPS measured** (`212 ms/frame`).
* Metrics: now the **held-out test split** values, with the per-class fire/smoke
  split shown as an honest limitation.
* Test count: 19 → **78**, and the description matches what the tests actually do.
* Dashboard: "visual badges" are now real runtime state; the "evidence modal"
  is the incident page that actually exists.
* FIRESENSE: the fire-negative clip is reported as **1 confirmed false alarm
  (down from 4)** rather than being glossed over.
* Latency: "~100 ms at 20 FPS" → "~0.4 s at ~5 FPS".

Files updated: [`generate_deck.py`](generate_deck.py) (regenerates both `.pptx`
copies), [`presentation.html`](presentation.html),
[`PRESENTATION.md`](PRESENTATION.md),
[`generate_deck.py`](generate_deck.py) → `FireWatch_AI_Presentation*.pptx`, and
[`create_download_page.py`](create_download_page.py) → `download.html` (now
self-contained; the old script read from a dead path outside the project).

---

## 4. How to verify

```powershell
cd "C:\Users\manna_2c83x\fire-detection-ai\firedetec2\fire-detection-ai"
& "C:\Users\manna_2c83x\fire-detection-ai\.venv\Scripts\python.exe" -m pytest
python app.py                      # http://127.0.0.1:5000 → "Start stream"
python evaluation/run_eval.py --data evaluation\datasets\dfire-test\data.yaml `
                             --negatives "C:\Users\manna_2c83x\fire-detection-ai\evaluation"
```

The suite leaves `fire_detection.db` and `snapshots/` untouched — verified by
running it repeatedly and comparing the database contents.

---

## 5. Round 2 — multi-camera readiness and deployment packaging

The two remaining objective items are done:

| Area | Change |
|---|---|
| Camera registry | [`services/camera_registry.py`](services/camera_registry.py) + a `cameras` table. Seeded on first start from `CAMERA_SOURCES` (or `CAMERA_SOURCE`), managed at runtime through `/api/cameras`. |
| Concurrent streams | [`services/camera_service.py`](services/camera_service.py) keeps one session **per camera**; `StreamBusy` is per camera, plus `stop_stream(id)` and `active_camera_ids()`. |
| Per-camera status | [`services/status_service.py`](services/status_service.py) tracks each camera separately; `/api/status` returns a `cameras` array alongside the aggregate fields. |
| Web UI | the dashboard shows a camera selector when more than one camera exists; the stream URL becomes `/video_feed?camera=<id>`. |
| Deployment | [`Dockerfile`](Dockerfile) (CPU-only, gunicorn + gthread so MJPEG does not block the API), [`.dockerignore`](.dockerignore), [`docker-compose.yml`](docker-compose.yml) with a data volume, [`deploy/firewatch.service`](deploy/firewatch.service) and [`deploy/run-windows.ps1`](deploy/run-windows.ps1). |
| Tests | 78. [`tests/test_cameras.py`](tests/test_cameras.py) covers registry seeding, deduplication, concurrent streams, per-camera stop, disabled cameras, and the camera API including the "cannot delete while streaming" guard. |

> The Docker image was **not built** in this environment: the Docker daemon is not
> running and there is no network access to pull a base image. The files are
> provided for a normal host; `docker compose up -d --build` is the entry point.

---

## 6. What is left (deliberately not done here)

1. **Smoke recall is 48 %.** This is a data/model problem, not a code problem.
   Fine-tune on `evaluation/negative-dfire` + more smoke samples; the recipe is in
   `training/train.py`.
2. **CPU speed.** 4.7 FPS at 640×480. Export to ONNX or OpenVINO (2–4× on CPU),
   or move to a small GPU.
3. **Authentication.** Still none — keep `HOST=127.0.0.1` or put it behind an
   authenticating reverse proxy before exposing it on a company network.
4. **Notification channels.** Only a local beep today; SMTP/Telegram/webhook is
   the next integration (`services/event_service.py` is the hook point).
5. **Hardware.** Several cameras now share one CPU; each stream costs a full
   inference pass per frame, so a GPU or an ONNX/OpenVINO export is the scaling
   lever.
