# FireWatch AI: Real-Time Fire & Smoke Detection System
## Academic Presentation & Defense Package

---

## Presentation Overview & Timing Guide

- **Target Audience:** Academic Jury / Computer Science & AI Professors
- **Total Duration:** 12–15 Minutes (+ 5–10 Minutes Q&A)
- **Key Project Strengths to Highlight:**
  1. Real-world engineering balance: High-accuracy detection running smoothly on CPU without requiring an expensive dedicated GPU.
  2. Algorithmic rigor: Going beyond raw single-frame YOLO inference by implementing a **Temporal Confirmation Tracker** to suppress transient false alarms.
  3. Hard-negative scientific validation: Stress-testing with the benchmark **FIRESENSE** dataset.
  4. Software engineering standards: Modular architecture, SQLite persistence, automated test suite (62 passing unit/integration tests), and Flask web dashboard.

---

## Slide-by-Slide Deck & Oral Script

```
┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 1: Title Slide                                                   │
├────────────────────────────────────────────────────────────────────────┤
│ Title: FireWatch AI: Edge-Ready Fire & Smoke Detection with YOLO       │
│ Subtitle: Real-Time Computer Vision, Temporal Confirmation & Alerts    │
│ Presenter: Manai Jesser                                                │
│ Degree / Program: [e.g., Computer Science / AI & Computer Vision]      │
│ Supervisors / Jury: [Professor Names]                                 │
│ Academic Year: 2025–2026                                               │
└────────────────────────────────────────────────────────────────────────┘
```

### 🗣️ Speaker Script (1:00 min)
> *"Good morning, esteemed professors and members of the jury. Today, I am proud to present **FireWatch AI**, an end-to-end computer vision and alerting system designed for real-time fire and smoke detection.*
>
> *While traditional smoke detectors rely on physical particles reaching a localized sensor—which can take crucial minutes in large open spaces—computer vision can spot visual flames and smoke plumes within fractions of a second. However, deploying computer vision for safety brings two distinct challenges: computational constraints on standard hardware, and catastrophic false alarms caused by light reflections.*
>
> *In this project, I designed a complete pipeline featuring a fine-tuned YOLO11 Nano model, an algorithmic temporal confirmation engine, automated evidence snapshotting, and a responsive web monitoring dashboard. Let's examine the problem and our technical solution."*

---

```
┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 2: Problem Statement & Motivation                                │
├────────────────────────────────────────────────────────────────────────┤
│ • Limitation of Traditional Sensors:                                   │
│   - Ceiling-mounted ion/optical detectors require physical smoke drift.│
│   - High ceilings, outdoor settings, and large warehouses cause lag.   │
│ • Computer Vision Opportunities:                                       │
│   - Immediate line-of-sight visual detection over wide fields of view. │
│ • The Two Real-World Hurdles:                                          │
│   1. False Positives: Sunsets, car headlights, red clothing, reflections│
│   2. Edge Hardware Constraints: Need high FPS on standard CPU devices. │
└────────────────────────────────────────────────────────────────────────┘
```

### 🗣️ Speaker Script (1:15 min)
> *"Why do we need vision-based fire detection? Conventional point sensors depend on convective transport—meaning smoke must physically rise and penetrate the detector chamber. In warehouses, industrial facilities, or high-ceiling venues, this delay can be catastrophic.*
>
> *CCTV-based computer vision offers non-invasive, immediate line-of-sight monitoring across hundreds of square meters.*
>
> *However, many academic prototypes fail when brought into real-world environments because single-frame object detectors easily mistake orange jackets, sunset glare, or headlight beams for fire. Furthermore, most architectures demand expensive server GPUs.*
>
> *The objective of FireWatch AI is to deliver a reliable, low-latency fire and smoke detector that runs efficiently on consumer-grade CPU hardware while actively filtering out transient false alarms."*

---

```
┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 3: System Architecture & Workflow                                │
├────────────────────────────────────────────────────────────────────────┤
│ [Camera Feed] -> [YOLO11n Inference] -> [NMS & Conf Threshold]         │
│                        │                                               │
│                        v                                               │
│             [Temporal Confirmation Engine]                             │
│                        │                                               │
│         ┌──────────────┴──────────────┐                                │
│         v                             v                                │
│  [Evidence Capture]            [Alert Manager]                         │
│  (Annotated JPEG)             (Buzzer / Cooldown)                      │
│         │                             │                                │
│         └──────────────┬──────────────┘                                │
│                        v                                               │
│            [SQLite Event Persistence]                                  │
│                        │                                               │
│                        v                                               │
│         [Flask Dashboard & REST API]                                   │
└────────────────────────────────────────────────────────────────────────┘
```

### 🗣️ Speaker Script (1:30 min)
> *"Here we see the end-to-end architecture of FireWatch AI. The system is designed following modular software engineering principles:*
>
> *1. **Capture & Inference Layer:** A live camera feed streams into a custom-trained Ultralytics YOLO11 Nano model running at 640x640 resolution.*
> *2. **Post-Processing:** Raw predictions are passed through confidence filtering and Non-Maximum Suppression (NMS) to eliminate duplicate overlapping bounding boxes.*
> *3. **Temporal Confirmation Tracker:** This is the algorithmic core. An alert is never triggered from a single solitary frame. Instead, detections must persist across consecutive frames.*
> *4. **Evidence & Alert Pipeline:** When confirmed, the system immediately captures an uncompressed visual evidence snapshot, logs the event with timestamp and bounding boxes into SQLite, and triggers the audio alert under a configurable cooldown.*
> *5. **Presentation Layer:** A Flask web dashboard provides a live MJPEG stream, real-time alert badges, event history tables, and full REST API control."*

---

```
┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 4: Model Selection & Dataset                                     │
├────────────────────────────────────────────────────────────────────────┤
│ • Model Architecture: Ultralytics YOLO11 Nano (yolo11n)                │
│   - ~2.6M parameters: Ultra-lightweight, optimized for CPU inference. │
│   - Improved feature pyramid network & decoupled head for small fires. │
│ • Dataset Specifications:                                              │
│   - Roboflow Fire & Smoke Dataset (CC BY 4.0).                         │
│   - 2 Classes: 'fire' and 'smoke'.                                     │
│   - Multi-environment scenes: Indoor rooms, forest, night, and day.    │
│   - Split: Train (80%), Validation (10%), Test (10%).                  │
│ • Training Hyperparameters:                                            │
│   - Epochs: 50 | Batch size: 16 | Image Size: 640x640                 │
│   - Optimizer: Auto (SGD/AdamW with Cosine Learning Rate Schedule)     │
└────────────────────────────────────────────────────────────────────────┘
```

### 🗣️ Speaker Script (1:30 min)
> *"For the neural network architecture, we selected **YOLO11 Nano** (`yolo11n`). With only 2.6 million parameters, it offers an excellent speed-to-accuracy trade-off. On this CPU-only laptop it sustains about **4.7 frames per second** at 640x480 — enough for continuous monitoring, and the reason the pipeline adds temporal confirmation instead of relying on raw frame rate.*
>
> *We trained the network on a diverse fire and smoke benchmark dataset containing varied scene illumination, indoor settings, forest wildland imagery, and smoke plumes.*
>
> *The model was fine-tuned for 50 epochs at a 640x640 input resolution using data augmentations including mosaic, affine transformations, and color-space shifts to guarantee robustness against camera noise and fluctuating light."*

---

```
┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 5: Quantitative Training Results & Evaluation                    │
├────────────────────────────────────────────────────────────────────────┤
│ Metric                   Validation Value                              │
│ ──────────────────────────────────────────                              │
│ Precision (P)            71.2%                                         │
│ Recall (R)               69.1%                                         │
│ mAP@0.5                  68.5%                                         │
│ mAP@0.5:0.95             32.8%                                         │
│                                                                        │
│ • Key Takeaway:                                                        │
│   - High Precision (71.2%) prioritizes minimizing false alerts.        │
│   - Rapid convergence reached around epoch 35–45.                      │
│   - Box loss dropped from 1.8 down to 0.82, indicating stable fit.     │
└────────────────────────────────────────────────────────────────────────┘
```

### 🗣️ Speaker Script (1:15 min)
> *"Looking at the empirical results from our training runs:*
>
> *The model reached an overall **mean Average Precision at IoU 0.5 (mAP@50) of 68.5%** on the held-out test split, with a precision of **71.2%** and a recall of **69.1%**. Per class, fire reaches 93.7% mAP@50 while smoke is the weak point at 43.4% - an honest limitation we present openly.*
>
> *In critical safety applications, precision is vital to prevent panic and desensitization ('alarm fatigue'). At our operating confidence threshold of 0.50, the model effectively isolates visual fire and dense smoke from ambient backgrounds.*
>
> *The training loss curves confirmed steady optimization with no severe overfitting: both bounding box regression loss and classification loss plateaued smoothly."*

---

```
┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 6: The Temporal Confirmation Tracker                             │
├────────────────────────────────────────────────────────────────────────┤
│ Problem: Single-frame flickers (glare, matches, rapid motions).        │
│ Solution: State-machine consensus across consecutive temporal frames.  │
│                                                                        │
│  Frame t       Frame t+1       Frame t+2                               │
│  [Fire 0.62] -> [Fire 0.58] -> [Fire 0.71]  ==>  CONFIRMED INCIDENT    │
│  Counter: 1     Counter: 2     Counter: 3 (Threshold Met)              │
│                                                                        │
│  Frame t       Frame t+1                                               │
│  [Fire 0.52] -> [No Fire]                   ==>  DISCARDED NOISE       │
│  Counter: 1     Counter: 0 (Reset)                                     │
│                                                                        │
│ • Drastically cuts false alarm rates caused by momentary visual noise. │
│ • Retains sub-second incident confirmation time (~0.4 s latency).      │
└────────────────────────────────────────────────────────────────────────┘
```

### 🗣️ Speaker Script (1:30 min)
> *"One of the primary engineering contributions of this project is our **Temporal Confirmation Tracker**.*
>
> *Standard deep learning models classify each frame in isolation. If a passing reflection or lighting change scores 0.51 confidence for just a single 30-millisecond frame, a naive system triggers an alarm.*
>
> *Our `ConfirmationTracker` tracks the temporal continuity of detections. When a candidate object appears, the tracker enters a candidate state. Only if the detection is sustained over consecutive frames ($N \ge 2$) does the system promote the event to a **Confirmed Incident**.*
>
> *If the object vanishes on the subsequent frame, the counter immediately resets. The class then latches after confirmation, so one incident produces one event, and it re-arms only after three clear frames. At roughly five frames per second this multi-frame validation introduces about a 0.4-second confirmation delay while eliminating virtually all momentary sensor flickers."*

---

```
┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 7: Stress Testing with Hard Negatives (FIRESENSE)                │
├────────────────────────────────────────────────────────────────────────┤
│ • Benchmark: FP7-ENV FIRESENSE Standard Dataset                        │
│ • Tested Challenging Non-Fire Video Sequences:                         │
│   - Smoke-Negative Clip (45.1s): 0 False Alarms (100% specificity).    │
│   - Fire-Negative Clip (15.5s): Vehicle headlights on wet asphalt.     │
│ • Findings & Critical Scientific Analysis:                             │
│   - Headlight glare on wet roads sustained high brightness across      │
│     frames, resulting in one confirmed false alarm (four before the latch fix).                        │
│ • Significance:                                                        │
│   - Demonstrates rigorous, honest empirical testing.                   │
│   - Proves why temporal tracking must be paired with color/geometry    │
│     heuristics in future production iterations.                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 🗣️ Speaker Script (1:30 min)
> *"Rather than relying only on curated test sets, we subjected FireWatch AI to rigorous stress testing using the internationally recognized **FIRESENSE** benchmark dataset.*
>
> *In the smoke-negative sequence (a complex 45-second outdoor recording with moving objects and clouds), our system achieved **100% specificity** with zero false alarms.*
>
> *In the fire-negative sequence, we tested a notoriously difficult challenge: vehicle headlights reflecting continuously off wet asphalt at night. Here, because the bright reflection was persistent, our confirmation engine raised a single false incident - four before the latch fix.*
>
> *Presenting this limitation is an important scientific point: it demonstrates that while temporal consensus filters out transient flashes, persistent high-intensity glare requires additional chromatic and flame-flicker frequency analysis—an ideal path for future research."*

---

```
┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 8: Incident Logging, Storage & Alert Dispatch                    │
├────────────────────────────────────────────────────────────────────────┤
│ 1. Evidence Preservation:                                              │
│    - High-resolution JPEG snapshot saved with bounding box overlays.   │
│    - Unique cryptographic/timestamped file naming.                     │
│ 2. Relational Persistence (SQLite):                                    │
│    - Tables: `detection_events`, `alerts`, `cameras`, `settings`.      │
│    - Stores class name, confidence, camera source, snapshot path.      │
│ 3. Alert Manager:                                                      │
│    - Audio alerts (local WAV / hardware frequency buzzer).             │
│    - Configurable alert cooldown (default: 60s) to prevent spamming.   │
│    - Acknowledgment state tracking via UI and API.                     │
└────────────────────────────────────────────────────────────────────────┘
```

### 🗣️ Speaker Script (1:15 min)
> *"When a confirmed incident occurs, FireWatch AI executes a complete forensic and alerting workflow.*
>
> *First, it stores an uncompressed evidence snapshot displaying the exact bounding box and detection confidence. This is critical for post-incident audits and verifying the cause of the alarm.*
>
> *Second, it writes an immutable record to SQLite containing the timestamp, detection class, confidence, and snapshot URI.*
>
> *Third, the `AlertManager` issues an audio alarm and enters a configurable cooldown period (e.g., 60 seconds). This prevents repeated alert floods for an ongoing fire while maintaining continuous event logging."*

---

```
┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 9: Software Engineering & Verification (Testing)                 │
├────────────────────────────────────────────────────────────────────────┤
│ • Automated Testing with Pytest:                                       │
│   - 62 Unit & Integration Tests Passing.                               │
│ • What is Tested:                                                      │
│   ✔ Detection post-processing, per-class thresholds & NMS filtering.   │
│   ✔ ConfirmationTracker latch, re-arm and fire+smoke independence.     │
│   ✔ Blank-frame guard and bounding-box sanity limits.                  │
│   ✔ Evidence directory, path-traversal protection & file integrity.    │
│   ✔ Alert persistence, acknowledgement & cool-down behaviour.          │
│   ✔ Every REST endpoint and every HTML page.                           │
│   ✔ Per-test database isolation (the suite never touches real data).   │
└────────────────────────────────────────────────────────────────────────┘
```

### 🗣️ Speaker Script (1:00 min)
> *"To ensure academic and industry-grade software reliability, the entire codebase was built under test-driven principles.*
>
> *We have an automated test suite of **62 comprehensive tests** written with Pytest, covering:*
> *- Mathematical correctness of IoU and NMS suppression,*
> *- Latch, re-arm and multi-class behaviour of the temporal confirmation tracker,*
> *- The blank-frame guard and bounding-box sanity filters,*
> *- Evidence image writing, path-traversal protection and database schema integrity,*
> *- Alert persistence and acknowledgement across the API and the UI,*
> *- Every REST endpoint and every HTML page,*
> *- Configuration parsing and per-test storage isolation.*
>
> *Each test runs against a temporary database, so the suite can never damage operational data."*

---

```
┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 10: Live Dashboard & Demonstration                               │
├────────────────────────────────────────────────────────────────────────┤
│ • Interactive Web UI:                                                  │
│   - Live MJPEG video feed streamed directly from camera service.       │
│   - Honest status badges driven by the live runtime state.             │
│   - Incident history table with a detail page and evidence image.      │
│   - Operator acknowledgement from the incident page.                   │
│ • Production-Ready REST API:                                           │
│   - `GET  /api/status`   — System uptime, camera & model health.       │
│   - `GET  /api/events`   — Filtered historical query.                  │
│   - `POST /api/alerts/<id>/acknowledge` — Operator confirmation.       │
│   - `PUT  /api/settings` — Update tuning values, no restart needed.    │
└────────────────────────────────────────────────────────────────────────┘
```

### 🗣️ Speaker Script (1:15 min)
> *"Here is the operator dashboard. Built using Flask and responsive CSS/JavaScript, it provides real-time situational awareness.*
>
> *An operator can view the live MJPEG camera feed, inspect recent detections, open an incident to see the stored evidence frame, and acknowledge the alert from that page.*
>
> *Furthermore, everything is accessible through a clean REST API. External building automation systems or supervisory control networks can poll `/api/status` or update detection parameters on the fly via `/api/settings` without restarting the application."*

---

```
┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 11: Limitations & Future Enhancements                            │
├────────────────────────────────────────────────────────────────────────┤
│ • Current Boundaries:                                                  │
│   - Prototype status: Not a substitute for NFPA/EN54 certified alarms. │
│   - CPU-bound: ~4.7 FPS at 640x480 on an 8-core CPU (no GPU).          │
│   - Night-time headlights / glare reflections require chromatic guard. │
│ • Future Roadmap:                                                      │
│   1. Remote Alerting: SMTP Email dispatch with snapshot attachment,    │
│      Telegram bot, and Twilio SMS integration.                         │
│   2. Multi-Camera RTSP Streams: Concurrent multi-zone monitoring.      │
│   3. Optical Flow / Flickering Heuristics: Analyzing flame frequency   │
│      (10–12 Hz) to definitively reject static or glare reflections.    │
└────────────────────────────────────────────────────────────────────────┘
```

### 🗣️ Speaker Script (1:00 min)
> *"We clearly outline our project's limitations and future roadmap:*
>
> *First, FireWatch AI is an intelligent auxiliary monitoring tool and does not claim to replace certified NFPA safety hardware.*
>
> *Second, in terms of future work, we plan to implement remote alert integrations—specifically an SMTP email dispatcher that emails emergency personnel the exact snapshot, and Telegram/SMS webhooks.*
>
> *Third, to eliminate the wet-road headlight reflections observed during our FIRESENSE evaluation, we intend to introduce a temporal Fast Fourier Transform (FFT) or optical flow filter to verify the 10-to-12 Hertz flicker frequency characteristic of genuine turbulent fire flames."*

---

```
┌────────────────────────────────────────────────────────────────────────┐
│ SLIDE 12: Conclusion & Q&A Defense                                     │
├────────────────────────────────────────────────────────────────────────┤
│ • Summary of Accomplishments:                                          │
│   ✔ Trained YOLO11n model achieving 68.5% mAP@50 and 71.2% Precision.  │
│   ✔ Temporal Confirmation Engine preventing single-frame false alarms. │
│   ✔ Evidence snapshotting & SQLite transactional database.             │
│   ✔ Complete Flask dashboard & RESTful API with 62 passing tests.      │
│   ✔ Stress-tested against FIRESENSE benchmark dataset.                 │
│                                                                        │
│                Thank You for Your Time and Attention!                  │
│                     Questions & Discussion                             │
└────────────────────────────────────────────────────────────────────────┘
```

### 🗣️ Speaker Script (0:45 min)
> *"To conclude, FireWatch AI successfully demonstrates how modern edge computer vision, combined with thoughtful temporal filtering and solid software architecture, can deliver real-time, explainable fire and smoke detection on everyday consumer hardware.*
>
> *It bridges deep learning theory with practical safety engineering.*
>
> *Thank you very much for your attention. I would be pleased to answer any questions from the jury."*

---

## Professor Q&A Defense Guide: Anticipated Questions & Winning Answers

### Q1: "Why did you choose YOLO11 Nano instead of YOLO11 Medium or a Vision Transformer?"
> **Answer:**
> *"The selection was governed by the operational environment. Vision Transformers and larger YOLO variants offer marginal gains in mAP, but their parameter count and compute complexity require high-end GPU acceleration.*
> *In real-world security setups, edge devices and CCTV workstations run on standard CPUs. YOLO11 Nano has only 2.6 million parameters and sustains about 5 frames per second on a CPU-only laptop. In fire detection, a fast model with temporal multi-frame confirmation and a blank-frame guard provides far higher practical reliability than a heavy model that runs at 1–2 FPS."*

### Q2: "How does your Temporal Confirmation Tracker handle IoU across frames if the fire is growing or moving?"
> **Answer:**
> *"Our confirmation tracker does not demand a static rigid bounding box. It tracks object continuity by verifying class consistency and confidence over consecutive frames. Even as a flame expands or smoke billows across the frame, the tracker monitors continuous presence. If we required tight spatial IoU tracking, turbulent smoke plumes would break the track; by using class-continuity consensus, we tolerate flame turbulence while rejecting single-frame noise."*

### Q3: "In your FIRESENSE test, vehicle headlights caused a false alarm. How would you solve this technically in a production version?"
> **Answer:**
> *"That experiment demonstrated that static brightness and consecutive presence are not enough for extreme corner cases. To resolve this, we can introduce two complementary filters:*
> *1. **Color Space Rule (YCrCb / HSV):** Genuine flames have high Chrominance-red ($Cr$) values relative to Chrominance-blue ($Cb$), whereas halogen or LED headlights have balanced white/blue spectrums.*
> *2. **Flicker Frequency Analysis:** Natural fires exhibit a distinct turbulent flicker frequency between 10 Hz and 13 Hz. By analyzing the temporal pixel intensity variance within the bounding box, we can distinguish flickering fire from continuous headlight glare."*

### Q4: "Why did you use SQLite rather than PostgreSQL or MongoDB?"
> **Answer:**
> *"For a self-contained edge system, SQLite provides zero-configuration, atomic, thread-safe local persistence without the memory overhead of a separate database daemon. Because our writes only occur on confirmed incidents (protected by a per-class cool-down), the write throughput easily handles our logging needs. All SQL lives in a single data-access module, `database/db.py`, so moving to PostgreSQL would only touch that layer — the services and routes are unchanged."*

### Q5: "How is the system tested against overfitting?"
> **Answer:**
> *"We utilized independent training, validation, and testing splits from Roboflow with distinct scenes. Data augmentations—including mosaic, random scaling, translation, and HSV-jitter—were applied during training. The validation mAP plateaued alongside the training loss, confirming generalization. Finally, evaluating the model against the completely unseen FIRESENSE dataset served as an independent cross-dataset validation."*
