# FireWatch AI

Real-time fire and smoke detection on a normal CPU. A YOLO11n checkpoint watches a
webcam or RTSP stream, a temporal confirmation engine suppresses single-frame
false alarms, confirmed incidents are stored in SQLite with an evidence frame, and
a local Flask dashboard shows the live feed, alert history and incident detail.

> **Safety notice** — this is a monitoring prototype, not a certified fire alarm.
> It does not call emergency services. Do not use it as the only fire-safety
> measure in a building.

---

## What it does

```
camera / RTSP ──► frame-quality guard ──► YOLO11n ──► per-class thresholds
                                                          │
                                                    NMS + box filters
                                                          │
                                              temporal confirmation (N of M frames)
                                                          │
                        ┌─────────────────────────────────┼──────────────────────────┐
                        ▼                                 ▼                          ▼
                 evidence JPEG                    SQLite event              alert record + sound
                (snapshots/)                (detection_events)                    (alerts)
                        └────────────► Flask dashboard / REST API ◄─────────────────┘
```

Design decisions that matter:

* **Per-class temporal confirmation.** A class must appear in `CONFIRMATION_FRAMES`
  consecutive frames before an incident is raised. It then stays *latched* (one
  event, not one per frame) and re-arms only after it has been absent for
  `CONFIRMATION_RELEASE_FRAMES` frames. Fire and smoke are tracked independently,
  so a scene containing both confirms both.
* **Blank-frame guard.** A covered lens or a uniform wall produces a frame with
  almost no detail, and small detectors hallucinate on those frames. Frames below
  `MIN_FRAME_STD` are never sent to the model — that costs one grayscale pass
  instead of a full inference and removes a whole class of false alarms.
* **Box sanity filters.** Detections smaller than `MIN_BOX_AREA_RATIO` (sensor
  noise) or larger than `MAX_BOX_AREA_RATIO` (full-frame blobs) are dropped.
* **Fail-fast streaming.** The model and the camera are opened *before* the HTTP
  response is returned, so a missing model or an unplugged camera produces a
  JSON `503`, not a 200 followed by a broken stream.
* **Honest status.** `/api/status` reports what actually happened (camera state,
  model state, frames analysed, frames skipped), not hard-coded strings.
* **Multi-camera registry.** Cameras are rows in SQLite; each one can stream
  independently and `/video_feed?camera=<id>` selects which feed to watch.

---

## Quick start

```powershell
cd "C:\Users\manna_2c83x\fire-detection-ai\firedetec2\fire-detection-ai"

# 1. activate the virtual environment
& "C:\Users\manna_2c83x\fire-detection-ai\.venv\Scripts\Activate.ps1"

# 2. install dependencies (first time, or after changing requirements.txt)
pip install -r requirements.txt

# 3. optional local configuration
Copy-Item .env.example .env      # then edit .env

# 4. run
python app.py
```

Open <http://127.0.0.1:5000/> and press **Start stream**.

The checkpoint ships with the repository at `models/best.pt`, so no external path
configuration is required.

---

## Configuration

Every value can be set as an environment variable or in `.env` (a real environment
variable wins). The full list with defaults lives in `.env.example`.

| Variable | Default | Meaning |
|---|---|---|
| `HOST` / `PORT` | `127.0.0.1` / `5000` | Bind address. Keep local unless the network is trusted. |
| `DATABASE_PATH` | `fire_detection.db` | SQLite file. |
| `EVIDENCE_DIR` | `snapshots/` | Where evidence JPEGs are written. |
| `LOG_DIR` | `logs/` | Rotating log files (`firewatch.log`, 2 MB × 5). |
| `MODEL_PATH` | `models/best.pt` | YOLO checkpoint. |
| `CAMERA_SOURCE` | `0` | Webcam index, `rtsp://…` URL or video file. |
| `CAMERA_SOURCES` | *(unset)* | Comma/semicolon separated list that seeds the camera registry. |
| `CONFIDENCE_THRESHOLD` | `0.50` | Fallback threshold for classes without an entry. |
| `FIRE_CONFIDENCE_THRESHOLD` | `0.50` | Fire-specific threshold. |
| `SMOKE_CONFIDENCE_THRESHOLD` | `0.55` | Smoke-specific threshold. |
| `CONFIRMATION_FRAMES` | `2` | Consecutive frames required to confirm. |
| `CONFIRMATION_RELEASE_FRAMES` | `3` | Frames without a class before it re-arms. |
| `CONFIRMATION_COOLDOWN` | `5.0` | Minimum seconds between two confirmations of the same class. |
| `MIN_FRAME_STD` | `6.0` | Blank-frame cut-off (grayscale standard deviation). |
| `MIN_BOX_AREA_RATIO` / `MAX_BOX_AREA_RATIO` | `0.0004` / `0.92` | Box sanity limits. |
| `ALERT_COOLDOWN` | `60` | Seconds between audible notifications. |
| `ALERT_SOUND_ENABLED` | `True` | Play a beep/sound on a confirmed incident. |
| `LOGGING_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |

Camera examples:

```powershell
$env:CAMERA_SOURCE = "rtsp://user:pass@192.168.1.20:554/Streaming/Channels/101"
$env:CAMERA_SOURCE = "C:\clips\fire-demo.mp4"
```

### Multiple cameras

Cameras live in the `cameras` table and are seeded on first start from
`CAMERA_SOURCES` (or from `CAMERA_SOURCE` for a single one). Every camera can
stream at the same time; the dashboard shows a selector when more than one
exists.

```powershell
$env:CAMERA_SOURCES = "0,rtsp://192.168.1.20:554/Streaming/Channels/101"
```

Manage them at runtime through `/api/cameras`, and select a stream with
`GET /video_feed?camera=<id>`. A camera can be disabled or deleted — but not
while it is streaming.

---

## REST API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness + version. |
| `GET` | `/api/status` | Real camera/model/stream state, counts, uptime. |
| `GET` | `/api/events` | Events, filterable by `class`, `camera_source`, `alert_status`, `limit`. |
| `GET` | `/api/events/<id>` | One event. |
| `GET` | `/api/alerts` | Alert history. |
| `POST` | `/api/alerts/<id>/acknowledge` | Acknowledge one alert. |
| `GET` | `/api/metrics` | DB-derived counts + live counters. |
| `GET`/`PUT` | `/api/settings` | Read / update tuning values (applies to new capture sessions). |
| `GET`/`POST` | `/api/cameras` | List cameras with live state / add one. |
| `PATCH`/`DELETE` | `/api/cameras/<id>` | Enable or disable / remove a camera. |
| `GET` | `/api/camera/probe` | Try to open the configured (or `?camera_id=`) camera once. |
| `POST` | `/api/stream/stop` | Release one camera (`{"camera_id": 1}`) or all of them. |
| `GET` | `/video_feed` | MJPEG stream, `?camera=<id>`; `503` when unavailable, `409` when busy. |
| `GET` | `/history`, `/incident/<id>`, `/evidence/<id>` | Dashboard pages and evidence image. |

---

## Testing

```powershell
& "C:\Users\manna_2c83x\fire-detection-ai\.venv\Scripts\python.exe" -m pytest
```

The suite (78 tests) runs against a **temporary database and evidence directory**
created per test by `conftest.py`; it never touches `fire_detection.db` or
`snapshots/`.

Coverage highlights: confirmation state machine (latch, re-arm, multi-class,
cool-down), per-class thresholds, box filters, blank-frame guard, evidence
writing and path-traversal protection, alert persistence and acknowledgement,
settings validation, every API route and every HTML page.

---

## Evaluation

The trained checkpoint was validated on the held-out Roboflow split (521 test
images) and stress-tested on two hard-negative sets that contain no fire or smoke:

```powershell
python evaluation/run_eval.py --data "C:\Users\manna_2c83x\fire-detection-ai\dataset-raw\data.yaml" `
                              --negatives "C:\Users\manna_2c83x\fire-detection-ai\evaluation"
```

Results are written to `evaluation/reports/`. See
[`PRESENTATION.md`](PRESENTATION.md) and [`FINAL_REPORT_OUTLINE.md`](FINAL_REPORT_OUTLINE.md)
for how to present them.

Measured on the held-out test split (521 images, 578 instances) and two
hard-negative sets, CPU only:

| Metric | Value |
|---|---|
| mAP@50 | **0.685** |
| mAP@50-95 | 0.328 |
| Precision / Recall | 0.712 / 0.691 |
| mAP@50 — fire / smoke | **0.937** / **0.434** |
| Inference time (640×480, 8-core CPU) | ~212 ms/frame ≈ 4.7 FPS |
| False positives, 50 D-Fire negatives @ 0.5 | 4 % of images |
| FIRESENSE fire-negative clip | 7 raw detections → 1 confirmed false alarm |
| Blank frames (white / grey / black) | skipped before inference, 0 detections |

The model is the weakest part of the pipeline, and the split is uneven:
**fire detection is strong (93.7% mAP@50) while smoke is weak (43.4%)**. The
blank-frame guard and temporal confirmation contain the resulting false alarms,
but a retrain on hard negatives plus more smoke data is the real fix — see
"Limitations".

---

## Project layout

```
app.py                  Flask app factory, logging, error handlers
config.py               .env loader + every tunable
conftest.py             per-test isolation (temp DB + temp evidence dir)
detection/
  confirmation.py       per-class latch / re-arm state machine
  frame_guard.py        blank-frame detection
  manager.py            normalise → threshold → NMS → box filter → confirm
  postprocess.py        threshold filtering and NMS
  inference.py          small single-image inference helper
alerts/manager.py       alert records, acknowledgement, audible notification
database/db.py          SQLite schema and helpers
routes/api.py           JSON API
routes/web.py           pages + MJPEG stream
services/
  camera_registry.py    named camera sources (SQLite registry)
  camera_service.py     capture sessions, fail-fast start, RTSP, multi-camera
  event_service.py      event/alert persistence and queries
  evidence_service.py   snapshot writing + safe path resolution
  metrics_service.py    DB-derived metrics
  status_service.py     live runtime state (per camera + aggregate)
  evaluation_service.py precision/recall/F1 helpers
templates/              dashboard, history, incident detail, error page
tests/                  78 tests
training/train.py       training entry point
evaluation/run_eval.py  validation + negative-set harness
deploy/                 systemd unit + Windows launcher
Dockerfile              CPU-only image, gunicorn
docker-compose.yml      one-command deployment with a data volume
```

---

## Training

```powershell
cd "C:\Users\manna_2c83x\fire-detection-ai"
& ".\.venv\Scripts\python.exe" -c "from ultralytics import YOLO; YOLO('yolo11n.pt').train(data='dataset-raw/data.yaml', epochs=50, imgsz=640, batch=16, project='runs', name='fire_smoke_detector')"
```

The original run used the Roboflow "Fire-Smoke Detection" dataset (10,589 train /
1,017 val / 521 test images, CC BY 4.0) and took ~39 hours on CPU. Copy the best
checkpoint into `models/best.pt` afterwards.

---

## Deployment

### Docker (recommended for a server)

```powershell
docker compose up -d --build
```

or without compose:

```powershell
docker build -t firewatch-ai .
docker run --rm -p 5000:5000 -v firewatch-data:/data `
  -e CAMERA_SOURCE=rtsp://user:pass@host:554/stream firewatch-ai
```

The image is CPU-only and runs gunicorn with 8 threads, so the long-lived MJPEG
response does not block the JSON API. The database, evidence frames and logs all
live in the `firewatch-data` volume. Docker Desktop on Windows cannot pass a
webcam into a container — use an RTSP URL there.

### Linux service (systemd)

```bash
sudo useradd --system --create-home firewatch
sudo install -d -o firewatch -g firewatch /opt/firewatch
sudo rsync -a --exclude .venv --exclude .git ./ /opt/firewatch/
cd /opt/firewatch
sudo -u firewatch python3 -m venv .venv
sudo -u firewatch .venv/bin/pip install -r requirements.txt "gunicorn==23.0.0"
sudo cp deploy/firewatch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now firewatch
```

The unit binds to `127.0.0.1:5000` and runs with `ProtectSystem=strict`; put
nginx or Caddy in front if it must be reachable from the network.

### Windows

`deploy\run-windows.ps1` starts the app from the project virtual environment
with the right paths. For unattended operation, register it with NSSM or Task
Scheduler — the script's help block contains the NSSM command.

> The application has no authentication. Keep `HOST=127.0.0.1`, or put an
> authenticating reverse proxy in front of it before exposing it on a network.

---

## Limitations

* The model was trained without hard negatives; it still reacts to bright glare.
  Fine-tuning on `evaluation/` negatives is the highest-value next step.
* CPU-only inference runs at roughly 5 FPS at 640×480 — fine for monitoring,
  not for fast-moving scenes. A GPU or an ONNX/OpenVINO export is the fix.
* Several cameras share one CPU. Every stream runs its own inference pass per
  frame, so N cameras cost roughly N× the compute — plan one process per one or
  two cameras on a machine without a GPU.
* No authentication. Keep `HOST=127.0.0.1` or put the app behind a reverse proxy
  with auth before exposing it.
* Not a certified alarm system; no emergency-service integration.
