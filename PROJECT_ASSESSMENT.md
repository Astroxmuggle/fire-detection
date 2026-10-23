# FireWatch AI — Environment & Project State Assessment

**Date:** 2026-10-23
**Assessed by:** DeepSeek Harness (full environment probe + code review + live execution)
**Project root:** `C:\Users\manna_2c83x\fire-detection-ai\firedetec2\fire-detection-ai`

> **Status: pre-remediation snapshot.** Every P0/P1 defect listed below has since
> been fixed and verified — see [`REMEDIATION.md`](REMEDIATION.md) for what
> changed and the before/after measurements. This document is kept because it
> records the evidence behind each finding.

---

## 1. Executive summary

**What it is:** a working local prototype of a fire/smoke detection system — trained YOLO11n checkpoint (mAP@50 ≈ 0.67), Flask dashboard, SQLite event log, evidence snapshots, pytest suite (19 tests). The core pipeline genuinely runs end-to-end on this machine.

**What it is not yet:** a deployable company product. Four issues are blocking: (1) the model fires on **blank/featureless frames at 0.70+ confidence**, (2) a confirmation bug means **fire + smoke in the same frame never raises an alarm**, (3) the test suite **destroys the production database**, and (4) the project **has no version control** and lives untracked inside an unrelated public Git repo.

**Headline numbers measured today**

| Item | Claimed in deck | Measured reality |
|---|---|---|
| CPU throughput | 20–30 FPS | **4.7 FPS median** (212 ms/frame), 3.7 FPS mean |
| mAP@50 | 68.6 % | **67.06 %** (final epoch, `results.csv`) |
| Precision / Recall | 74.0 % / 68.6 % | **72.5 % / 66.8 %** |
| False positives (D-Fire, 50 negatives) | 100 % specificity implied | **4 % of images at conf 0.5**, 14 % at 0.3 |
| Blank wall test | — | **fire @ 0.725** on a uniform white frame |
| Test suite | 19/19 pass | 19/19 pass **outside the sandbox** (18/19 inside it, tmpdir limitation) |

---

## 2. Environment state

### 2.1 Machine

| | |
|---|---|
| OS | Windows 11, build 26300 (NT 10.0) |
| CPU | Intel Family 6 Model 140, **8 logical cores** |
| GPU | **none** (`torch.cuda.is_available() == False`) |
| Python (venv) | 3.13.2 — `C:\Users\manna_2c83x\fire-detection-ai\.venv\Scripts\python.exe` |
| Python (global) | 3.13.2 — `C:\Python313\python.exe` (numpy, pillow, python-pptx only — **not usable for this project**) |
| Container tooling | Docker Desktop installed, no project containerisation |
| Other | ffmpeg, git, node/npm available; **no `pnpm`**, **no `nvidia-smi`** |

### 2.2 Dependencies — `requirements.txt` vs installed venv

| Package | Required | Installed | |
|---|---|---|---|
| Flask | 3.1.0 | 3.1.0 | OK |
| torch | 2.6.0 | 2.6.0+cpu | OK |
| torchvision | 0.21.0 | 0.21.0 | OK |
| Pillow | 11.3.0 | 11.3.0 | OK |
| pytest | 8.3.4 | 8.3.4 | OK |
| requests | 2.32.3 | 2.32.3 | OK |
| flask-cors | 5.0.0 | 5.0.0 | OK (but **never imported** in the code) |
| numpy | 2.1.1 | **2.5.3** | drift |
| opencv-python | 4.11.0.86 | **5.0.0.93** | major-version drift |
| ultralytics | 8.3.70 | **8.4.165** | drift |
| SQLAlchemy | 2.0.36 | **NOT INSTALLED** | `database/models.py` is unimportable |

The venv is 1.9 GB. `pip install -r requirements.txt` **today would downgrade** opencv/ultralytics/numpy and install SQLAlchemy — the environment is not reproducible from the file.

### 2.3 Model artefacts

* Checkpoint used by the app: `C:\Users\manna_2c83x\runs\detect\fire_smoke_detector\weights\best.pt` — **5,473,370 bytes, present and healthy**, classes `{0: fire, 1: smoke}`, task `detect`, loads in 0.07 s.
* Training run: 50 epochs, imgsz 640, batch 16, **no GPU** — total wall time **141,273 s ≈ 39 hours**.
* Training curves, confusion matrices, val batches all present in that `runs/` folder — good material for the report.
* **The model lives outside the repository.** `config.py:23` hard-codes an absolute path into a user profile; nothing in the repo will run on another machine without editing code or setting an env var.
* An unfinished hard-negative fine-tune exists (`evaluation/firesense-negative/runs/hard_negative_candidate/`) with **no weights** — the work was started and abandoned.

### 2.4 Dataset state — fragmented

| Location | Contents |
|---|---|
| `<root>/dataset-raw/` | **only `data.yaml`** — points at `../train/images`, `../val/images`, `../test/images` which **do not exist**. Dead config. |
| `C:\Users\manna_2c83x\fire-detection-ai\dataset-raw\` | **the real dataset**: 10,589 train, 1,017 valid, 521 test images **with YOLO labels** |
| `C:\Users\manna_2c83x\fire-detection-ai\Fire -smoke Detection.v1i.yolov11.zip` | 412 MB source archive, 24,266 entries (Roboflow, CC BY 4.0) |
| `…\evaluation\negative-dfire\` | 50 curated hard-negative images + manifest |
| `…\evaluation\firesense-negative\` | FIRESENSE negative clips + **honest README of the false positive they found** |
| `…\dataset\`, `…\datatset\` (sic) | near-empty leftovers, 0–1 files each |

Conclusion: the data exists but is **not inside the project and not wired to any script**.

---

## 3. What actually works (verified by execution, not by reading)

* `python app.py` starts and serves on `http://127.0.0.1:5000` — verified over real HTTP.
* `GET /` and `/dashboard` → 200, rendered HTML (2,066 bytes).
* `GET /api/health` → `{"status":"healthy"}`; `/api/events`, `/api/alerts`, `/api/settings`, `/api/status`, `/api/metrics` → 200 with real JSON.
* SQLite schema is created on boot (`init_db()`), events/alerts persist correctly.
* Detection pipeline: YOLO inference → threshold filter → NMS → confirmation → event + snapshot + alert. Verified genuine detections on real footage (`fire @ 0.52`, `smoke @ 0.64` on the stored snapshots).
* Evidence snapshots are written as valid JPEGs with sanitised filenames.
* 19 pytest tests, **19/19 green outside the sandbox**.
* Documentation/deck assets are extensive: `README.md`, `DEFENSE_CHECKLIST.md`, `FINAL_REPORT_OUTLINE.md`, `PRESENTATION.md` (378 lines of speaker script), 12-slide PPTX, HTML deck, self-contained download page.

---

## 4. Defects — ranked by business impact

### P0 — must fix before any demo or deployment

**1. Blank-frame false positives (model quality)**
`_probe` results on uniform frames at conf 0.5:

| Frame | Detection |
|---|---|
| white (245) | **fire 0.725** |
| light grey (200) | **fire 0.701** |
| mid grey (128) | **fire 0.562** |
| black (5) | smoke 0.30 |

A covered lens, a white wall, or a frosted window will raise a confirmed fire alarm. This also explains the 80×80 black frames in `snapshots/` that were stored as "fire" events.
On the 50-image D-Fire negative set: **2/50 (4 %) false positives at 0.5**, 3/50 at 0.4, 7/50 (14 %) at 0.3.
On the FIRESENSE `fire_negative.avi`: **7 raw detections → 4 confirmed false incidents** (headlight glare on wet road) — exactly what `evaluation/firesense-negative/README.md` already documents honestly.

**2. Fire + smoke in one frame never confirms**
`detection/manager.py:55-65` calls `confirmation.update()` **once per detection per frame**, and `ConfirmationTracker.update()` (`detection/confirmation.py:44-46`) **erases every other class' counter**. Measured: 5 consecutive frames each containing fire *and* smoke → `[0, 0, 0, 0, 0]` — **no event ever raised**. Since a real fire produces both classes, this silently disables detection in the most important scenario. Single-class frames work (`[0,1,1,1,1]`).

**3. The test suite wipes production data**
`tests/test_api.py:10` calls `clear_event_history()`, which runs `DELETE FROM detection_events` (`services/event_service.py:120-124`).
Evidence seen today: `detection_events` max id **49** with **1 row**, but **76 orphaned alerts** pointing at deleted events. Tests also write snapshots straight into the real `snapshots/` folder (**45 of 49 stored `.jpg` are <1 KB test artefacts** such as 80×80 black frames). Every `pytest` run destroys the operator's incident history.

**4. No version control**
There is **no `.git`** in the project. Worse, the project sits untracked inside the user's **home directory repository** `C:\Users\manna_2c83x`, which is a clone of the unrelated public `github.com/Astroxmuggle/THE-YEAR-OF-GRETA` (237 untracked/modified entries). A careless `git add -A` there would push company code into an unrelated public repository. No `.gitignore`, no `.env`, no LICENSE.

### P1 — correctness and honesty of the delivered product

**5. Incident detail page is broken (500)**
`templates/incident_detail.html` uses fields that do not exist: `incident.class`, `incident.timestamp`, `incident.evidence_image`, and posts the acknowledge form to the wrong endpoint with an event id where an *alert* id is expected. `GET /incident/49` → `UndefinedError: 'dict object' has no attribute 'evidence_image'`. Route works only because the template is never rendered with real data.
Additionally, snapshots live in `<root>/snapshots`, not in `static/`, and **there is no route serving them** — evidence can never be displayed even after the template is fixed.

**6. `base.html` cannot render**
References `web.incident_history` and `web.settings` — neither route exists → `BuildError`. It is currently dead code that will break the moment anyone extends a page from it.

**7. Status and metrics endpoints report fiction**
`routes/api.py:21-22` hard-codes `"camera_status": "online"` and `"model_status": "loaded"` — true only if a camera exists; here `/video_feed` returns 500, yet the API says "online". `services/metrics_service.py:41` builds a fresh `MetricsService` per request, so `confirmed_incidents` is **always 0** (verified: 1 real event, endpoint returned 0).

**8. Live detections are never counted as confirmed**
`services/camera_service.py:86` stores events with `alert_status='pending'`, while `routes/api.py:24` counts "confirmed incidents" as anything `!= 'pending'`. So the dashboard's *Confirmed incidents* KPI stays at 0 for genuine alarms.

**9. `/video_feed` error handling is ineffective**
`routes/web.py:18-24` wraps `Response(generate_stream())` in `try/except`, but the generator is lazy — the `RuntimeError: Could not open camera index 0` is raised during streaming, after the 200 goes out. Client receives **HTTP 500** with no useful message (verified over HTTP).

**10. `.env` is never loaded**
`config.py` reads `os.environ` only; there is no `python-dotenv` anywhere. `README.md:47-51` tells the user to copy `.env.example` → `.env` and implies it will take effect. It will not.

**11. Confirmation never re-arms**
After the threshold is reached, `update()` keeps returning `True` on every subsequent frame (`[0,1,1,1,1]`). The only thing preventing an event flood is the ad-hoc 5-second de-duplication in `camera_service.py:79`; `AlertManager`'s cooldown is defeated because `create_confirmed_event` instantiates it with `alert_cooldown=0` every call (`services/event_service.py:68`).

**12. Retraining is not reproducible from the repo**
`training/train.py` fails three ways: it writes to `models/` which is a **40-byte placeholder file, not a directory**; it loads that same non-existent file as the base model instead of `yolo11n.pt`; and it points at `dataset-raw/data.yaml` whose image paths do not exist.

### P2 — engineering hygiene

* `database/models.py` — dead SQLAlchemy layer, schema contradicts `db.py` (uses `timestamp` vs `created_at`, tables `cameras`/`settings` that do not exist) and references an unimported `Boolean`. Nothing imports it.
* Unused modules: `detection/camera.py`, `alerts/sounds.py`, `services/evaluation_service.py`, `detection/inference.py` (tests only), `detection/postprocess.process_detections` (duplicate of the manager's).
* `LOGGING_LEVEL` is configured (`config.py:33`) but **never used** — no logging at all; `logs` is a placeholder *file*.
* `logs` and `models` are 40-byte text files masquerading as directories — this will trip up anyone (or any tool) that assumes they are folders.
* `snapshots/fire_camera` and `snapshots/smoke_camera` are 0-byte files, again colliding with the naming of real snapshots.
* `pytest.ini` lives **one level above the project** (`…\fire-detection-ai\pytest.ini`) with `pythonpath = firedetec2/fire-detection-ai`. Copy the project elsewhere and every import fails. No `conftest.py`, no `[tool.pytest]` in-repo.
* Dashboard JS writes event fields with `innerHTML` (`static/js/app.js:38-44`) — stored-XSS pattern if a camera source/class name ever becomes attacker-controlled.
* No authentication, no CSRF protection, no rate limiting on any route. Fine on `127.0.0.1`, unacceptable the moment `HOST=0.0.0.0` for a company network.
* No Dockerfile, no CI, no migrations, no retention policy for `snapshots/` or `events`.
* Duplicated deck artefacts (`FireWatch_AI_Presentation.pptx` and `…_Manai_Jesser.pptx` are byte-identical, 918,683 B each); `download.html` embeds the deck as base64 and was generated from a path outside the project (`C:\Users\manna_2c83x\.gemini\antigravity\brain\…`).

---

## 5. Deck / report vs reality — defense risk

The presentation makes claims the running system does not support. These are the questions a jury will ask:

| Claim (slide) | Reality |
|---|---|
| "20–30+ FPS on CPU" (slides 4, 12; `PRESENTATION.md:121,360`) | **4.7 FPS** measured on this exact machine |
| "0 raw fire detections, 0 confirmed incidents, specificity 100 %" on FIRESENSE (slide 8) | Accurate **for the smoke clip**, which is what the card says. The same slide's second card does report the fire clip honestly (7 detections / 4 confirmed false alarms). The risk is the headline alone, which a jury may read as "no false alarms at all". |
| "Camera Online / Model Loaded badges" (slide 11) | Hard-coded strings, not status |
| "19 automated tests, 100 % pass" (slides 10, 12) | True (19 pass), but the suite **deletes the production event log** when it runs |
| "RTSP or Webcam input" (slide 3) | Webcam index only — `get_camera_capture` casts the source to `int`, so an RTSP URL raises `ValueError` |
| Precision 74.0 % / Recall 68.6 % / mAP@50 68.6 % (slide 5) | 72.5 % / 66.8 % / 67.06 % in the final epoch of `results.csv` |

The deck is strong on structure and narrative; the numbers need a five-minute correction pass before the defense. Note the deck and `PRESENTATION.md` **do** contain a Q&A answer about the headlight false positive (`PRESENTATION.md:366`), so the honest version is already half-written.

---

## 6. What is actually needed (prioritised plan)

### P0 — 1 to 2 days, makes the project defensible
1. **Fix the confirmation state machine.** Track counts per class (`dict[class_name] -> streak`) instead of one global counter; evaluate all detections in a frame before updating; re-arm only after a configurable cool-down, not "confirm forever". Add the two regression tests (fire+smoke, re-arm).
2. **Isolate tests from production.** Per-test temp database + temp snapshot dir (fixture in `conftest.py`), never `clear_event_history()` on the real DB. Restore a clean `fire_detection.db` and purge the 45 test-gen snapshots.
3. **Initialise Git properly.** `git init` **inside the project**, add `.gitignore` (`__pycache__/`, `.venv/`, `*.db`, `snapshots/*.jpg`, `*.pt`, `.env`), commit history. Do **not** commit from the home directory.
4. **Correct the deck numbers** (FPS, precision/recall/mAP, FIRESENSE wording) and replace "20–30 FPS" with the measured figure.

### P1 — about a week, makes it a product
5. **Reduce false positives.** Cheapest first: per-class thresholds (fire 0.6+, smoke 0.55+), a minimum-bbox-area filter, a temporal "N of M frames" rule instead of strict consecutiveness, and a static-scene/blank-frame guard (variance check) — the blank-frame failure is trivially filtered by rejecting near-uniform frames. Then fine-tune on the existing hard-negative material (`evaluation/negative-dfire`, FIRESENSE clips) — that dataset is already prepared and the abandoned run shows the recipe.
6. **Fix the incident page** (field names + acknowledge endpoint), serve `/snapshots/<file>` or `/incident/<id>/evidence`, and make `base.html` render (add the missing routes or delete the template).
7. **Make status honest:** real camera probe, real model-loaded flag, real metrics from the DB, correct "confirmed" semantics (`alert_status='confirmed'`).
8. **Config that works:** bundle the checkpoint inside the repo (`models/best.pt` — make `models/` a real directory), load `.env` with `python-dotenv`, remove the absolute path from `config.py`.
9. **Fix `/video_feed`** — validate the camera before returning the `Response`, return 503 JSON, and release the capture on disconnect.

### P2 — before the company rollout
10. **Run it as a service** (NSSM/Task Scheduler or a Docker image), with rotation of logs and snapshots.
11. **Add auth** (a simple token or login) and bind to `127.0.0.1` unless the network is trusted.
12. **Multi-camera / RTSP**: `cv2.VideoCapture` accepts a URL string — the only blocker is the `int()` cast. A camera registry table would follow naturally (the abandoned `database/models.py` already sketches it).
13. **Real evaluation harness**: a `evaluation/run_eval.py` that computes precision/recall/mAP on the 521-image test split and the negative sets, writes a JSON report. Right now the numbers come from training logs only.
14. **Notification channel** (email/Telegram/webhook) — the deck promises alerting; today it only beeps locally via `winsound`.

---

## 7. Environment quirks found (not project bugs)

* **`.pytest_cache/` in the project root has a broken ACL** (created 09/10 by a sandboxed run): its DACL grants only SYSTEM / Administrators / "OWNER RIGHTS", so a sandboxed process cannot read it. Outside a sandbox the owner still has full control, so `Remove-Item .pytest_cache -Recurse -Force` from a normal PowerShell cleans it up.
* **Inside this harness only:** Python 3.13's `os.mkdir(path, 0o700)` creates directories the sandboxed process can no longer list or delete. That is why pytest's `tmp_path` fixture failed here (`1 error`), and it is why the four probe folders I created had to be removed with elevated approval. The exact same test **passes when run outside the sandbox** (`1 passed in 15.84s`) — so this is a harness limitation, not something wrong with the project. Your own PowerShell is unaffected.
* My probe runs left the DB as they found it except for the damage described in defect #3: the earlier `pytest` run added one test event (`id 49`) and cleared the events that existed before it. Alerts (77 rows) are intact.

---

## 8. Bottom line

The engineering skeleton is real and the demo runs. The gap to "company project" is not size — it is **trust**: the model alarms on blank walls, the alarm path breaks when fire and smoke appear together, and running the test suite erases the incident history. Fix those three, correct the deck numbers, put the project in its own Git repository, and this becomes presentable both to a jury and to a technical stakeholder.
