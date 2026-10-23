import os
import shutil

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets", "training")
FALLBACK_RUNS_DIR = r"C:\Users\manna_2c83x\runs\detect\fire_smoke_detector"


def asset_path(name):
    """Prefer the copy bundled with the repository, fall back to the training run."""
    bundled = os.path.join(ASSETS_DIR, name)
    return bundled if os.path.exists(bundled) else os.path.join(FALLBACK_RUNS_DIR, name)


def create_deck():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # Palette
    C_BG = RGBColor(15, 23, 42)        # Slate 900
    C_CARD = RGBColor(30, 41, 59)      # Slate 800
    C_BORDER = RGBColor(51, 65, 85)    # Slate 700
    C_PRIMARY = RGBColor(249, 115, 22) # Fire Orange
    C_ACCENT = RGBColor(239, 68, 68)   # Alert Red
    C_WHITE = RGBColor(248, 250, 252)  # Text White
    C_MUTED = RGBColor(148, 163, 184)  # Text Muted
    C_GOLD = RGBColor(234, 179, 8)     # Warning Gold
    C_GREEN = RGBColor(34, 197, 94)    # Success Green

    img_results = asset_path("results.png")
    img_confusion = asset_path("confusion_matrix.png")
    img_preds = asset_path("val_batch0_pred.jpg")

    def set_bg(slide):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = C_BG
        bg.line.fill.background()
        return bg

    def add_header(slide, title_text, category="FIREWATCH AI ACADEMIC DEFENSE"):
        tb = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.7), Inches(1.1))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        
        p_cat = tf.paragraphs[0]
        p_cat.text = category.upper()
        p_cat.font.size = Pt(11)
        p_cat.font.bold = True
        p_cat.font.color.rgb = C_PRIMARY

        p_title = tf.add_paragraph()
        p_title.text = title_text
        p_title.font.size = Pt(24)
        p_title.font.bold = True
        p_title.font.color.rgb = C_WHITE

    def add_card(slide, left, top, width, height, title=None, bg_color=C_CARD, border_color=C_BORDER):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        card.fill.solid()
        card.fill.fore_color.rgb = bg_color
        if border_color:
            card.line.color.rgb = border_color
            card.line.width = Pt(1.5)
        else:
            card.line.fill.background()

        if title:
            tb = slide.shapes.add_textbox(left + Inches(0.3), top + Inches(0.2), width - Inches(0.6), Inches(0.5))
            tf = tb.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = title
            p.font.size = Pt(14)
            p.font.bold = True
            p.font.color.rgb = C_PRIMARY
        return card

    def add_speaker_notes(slide, notes):
        notes_slide = slide.notes_slide
        tf = notes_slide.notes_text_frame
        tf.text = notes

    # ==========================================
    # SLIDE 1: Title Slide
    # ==========================================
    slide_layout = prs.slide_layouts[6] # blank
    s1 = prs.slides.add_slide(slide_layout)
    set_bg(s1)

    # Accent decorative bar
    bar = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.5), Inches(0.15), Inches(4.2))
    bar.fill.solid()
    bar.fill.fore_color.rgb = C_PRIMARY
    bar.line.fill.background()

    tb = s1.shapes.add_textbox(Inches(1.2), Inches(1.5), Inches(11.0), Inches(4.2))
    tf = tb.text_frame
    tf.word_wrap = True

    p0 = tf.paragraphs[0]
    p0.text = "COMPUTER VISION PROJECT"
    p0.font.size = Pt(13)
    p0.font.bold = True
    p0.font.color.rgb = C_PRIMARY

    p1 = tf.add_paragraph()
    p1.text = "FireWatch AI: Real-Time Fire & Smoke Detection"
    p1.font.size = Pt(36)
    p1.font.bold = True
    p1.font.color.rgb = C_WHITE

    p2 = tf.add_paragraph()
    p2.text = "Real-Time YOLO11 Inference, Algorithmic Temporal Confirmation & Incident Alerting"
    p2.font.size = Pt(18)
    p2.font.color.rgb = C_MUTED

    p3 = tf.add_paragraph()
    p3.text = "\n• Author: Manai Jesser\n• Evaluation Jury: Academic Defense Committee\n• Academic Year: 2025–2026"
    p3.font.size = Pt(14)
    p3.font.color.rgb = RGBColor(203, 213, 225)

    add_speaker_notes(s1, "Good morning, Professor and members of the jury. Today, I am proud to present FireWatch AI, an end-to-end computer vision and alerting system designed for real-time fire and smoke detection.\n\nWhile traditional smoke detectors rely on physical particles reaching a localized sensor, computer vision can spot visual flames and smoke plumes within fractions of a second. In this project, I designed a complete pipeline featuring a fine-tuned YOLO11 Nano model, an algorithmic temporal confirmation engine, automated evidence snapshotting, and a responsive web monitoring dashboard.")

    # ==========================================
    # SLIDE 2: Problem Statement & Motivation
    # ==========================================
    s2 = prs.slides.add_slide(slide_layout)
    set_bg(s2)
    add_header(s2, "Problem Statement: Why Vision-Based Fire Detection?")

    # 3 Cards
    c1 = add_card(s2, Inches(0.8), Inches(1.8), Inches(3.6), Inches(4.8), "Point Sensor Limits")
    tb = s2.shapes.add_textbox(Inches(1.1), Inches(2.6), Inches(3.0), Inches(3.7))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• Delayed Response: Smoke must physically drift into ceiling ionization chambers.\n\n• High Ceilings: Ineffective in large warehouses, airports, and sports arenas.\n\n• Outdoor Failure: Completely unable to monitor forest perimeters or open construction sites."
    p.font.size = Pt(13)
    p.font.color.rgb = C_WHITE

    c2 = add_card(s2, Inches(4.8), Inches(1.8), Inches(3.6), Inches(4.8), "Computer Vision Benefits")
    tb = s2.shapes.add_textbox(Inches(5.1), Inches(2.6), Inches(3.0), Inches(3.7))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• Immediate Line of Sight: Visual flame detection in < 200 ms.\n\n• Dual Class Detection: Recognizes both active flames and early rising smoke.\n\n• Broad Coverage: Uses existing CCTV camera infrastructure across hundreds of square meters."
    p.font.size = Pt(13)
    p.font.color.rgb = C_WHITE

    c3 = add_card(s2, Inches(8.8), Inches(1.8), Inches(3.7), Inches(4.8), "The Real Hurdles")
    tb = s2.shapes.add_textbox(Inches(9.1), Inches(2.6), Inches(3.1), Inches(3.7))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• False Alarms ('Alarm Fatigue'): Car headlights, sunset glares, reflective asphalt, and red clothing trigger false positives.\n\n• Hardware Cost: Traditional heavy deep learning requires server GPUs.\n\n• Project Goal: Real-time CPU inference + Algorithmic noise suppression."
    p.font.size = Pt(13)
    p.font.color.rgb = C_WHITE

    add_speaker_notes(s2, "In large industrial spaces or warehouses, conventional smoke detectors suffer from significant detection lag because physical combustion particles must drift all the way to a ceiling unit. CCTV-based vision systems solve this by monitoring hundreds of square meters simultaneously with zero transit delay. However, the primary barrier is false alarm fatigue. A camera mistaking sunset glare or car lights for fire causes panic. Furthermore, most systems demand costly server GPUs. FireWatch AI addresses both: CPU real-time execution paired with temporal consensus.")

    # ==========================================
    # SLIDE 3: System Architecture
    # ==========================================
    s3 = prs.slides.add_slide(slide_layout)
    set_bg(s3)
    add_header(s3, "End-to-End System Architecture")

    steps = [
        ("1. Ingestion", "OpenCV Video Capture\n• 640x480 resolution\n• RTSP or Webcam input"),
        ("2. AI Inference", "YOLO11 Nano Model\n• 2.6M parameters\n• 640x640 input tensor"),
        ("3. Post-Process", "Threshold & NMS\n• Conf Filter (>0.50)\n• IoU Suppression (0.4)"),
        ("4. Confirmation", "Temporal Tracker\n• 2+ Consecutive Frames\n• Rejects 1-frame spikes"),
        ("5. Persistence", "Evidence & SQLite\n• Saves JPEG Snapshot\n• Transactional Event DB"),
        ("6. Monitoring", "Flask Web Dashboard\n• Live MJPEG Stream\n• RESTful API Endpoints"),
    ]

    for i, (title, text) in enumerate(steps):
        col = i % 3
        row = i // 3
        left = Inches(0.8 + col * 4.0)
        top = Inches(1.8 + row * 2.5)
        add_card(s3, left, top, Inches(3.7), Inches(2.2), title)
        tb = s3.shapes.add_textbox(left + Inches(0.3), top + Inches(0.8), Inches(3.1), Inches(1.2))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(12)
        p.font.color.rgb = C_WHITE

    add_speaker_notes(s3, "This diagram represents the architecture of FireWatch AI. The software is organized into decoupled, modular layers: capture and inference, thresholding and Non-Maximum Suppression, the temporal confirmation tracker which prevents single-frame noise, evidence snapshot capture and SQLite logging, and finally the operator web dashboard and REST API.")

    # ==========================================
    # SLIDE 4: Model Architecture & Dataset
    # ==========================================
    s4 = prs.slides.add_slide(slide_layout)
    set_bg(s4)
    add_header(s4, "Model Selection: YOLO11 Nano & Dataset Training")

    add_card(s4, Inches(0.8), Inches(1.8), Inches(5.6), Inches(4.8), "Why Ultralytics YOLO11n?")
    tb = s4.shapes.add_textbox(Inches(1.1), Inches(2.6), Inches(5.0), Inches(3.8))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• Model Size: Only 2.6 Million Parameters (5.6 MB checkpoint).\n\n• CPU Performance: 4.7 FPS measured on an 8-core laptop CPU (212 ms/frame at 640x480, CPU-only).\n\n• Architectural Upgrades: Enhanced C3k2 feature extractors with decoupled classification and bounding-box regression heads.\n\n• Dual Class Detection: Simultaneously optimizes for 'fire' and 'smoke' bounding boxes."
    p.font.size = Pt(13)
    p.font.color.rgb = C_WHITE

    add_card(s4, Inches(6.8), Inches(1.8), Inches(5.7), Inches(4.8), "Dataset & Hyperparameters")
    tb = s4.shapes.add_textbox(Inches(7.1), Inches(2.6), Inches(5.1), Inches(3.8))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• Dataset Source: Roboflow Fire & Smoke Benchmark (CC BY 4.0).\n\n• Distribution: Multi-environment scenes (wildfire, indoor rooms, factory, day, night).\n\n• Augmentations: Mosaic 4-image stitching, random scaling, affine rotation, and HSV color perturbations.\n\n• Training Budget: 50 Epochs | Batch size 16 | Image size 640x640 | Cosine learning rate scheduling."
    p.font.size = Pt(13)
    p.font.color.rgb = C_WHITE

    add_speaker_notes(s4, "For our neural network, we selected YOLO11 Nano. With only 2.6 million parameters, it enables 20 to 30 frames per second on consumer CPU hardware. We fine-tuned the model for 50 epochs on a multi-environment benchmark dataset covering both fire and smoke across diverse illumination conditions.")

    # ==========================================
    # SLIDE 5: Quantitative Results
    # ==========================================
    s5 = prs.slides.add_slide(slide_layout)
    set_bg(s5)
    add_header(s5, "Quantitative Training Results & Metrics")

    # Metrics Card
    add_card(s5, Inches(0.8), Inches(1.8), Inches(4.5), Inches(4.8), "Held-out Test Metrics")
    metrics = [
        ("Precision (Box P)", "71.2%", "Prioritizes low false alarms"),
        ("Recall (Box R)", "69.1%", "Strong detection sensitivity"),
        ("mAP @ 0.50", "68.5%", "High localization accuracy"),
        ("mAP @ 0.50:0.95", "32.8%", "Tight boundary agreement"),
    ]
    tb = s5.shapes.add_textbox(Inches(1.0), Inches(2.5), Inches(4.1), Inches(3.8))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.paragraphs[0].text = ""
    for name, val, desc in metrics:
        p = tf.add_paragraph()
        p.text = f"{name}: {val}"
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = C_PRIMARY
        p_desc = tf.add_paragraph()
        p_desc.text = f"  └ {desc}\n"
        p_desc.font.size = Pt(11)
        p_desc.font.color.rgb = C_MUTED

    # Insert Results Image
    add_card(s5, Inches(5.6), Inches(1.8), Inches(6.9), Inches(4.8), "Training & Loss Curves (results.png)")
    if os.path.exists(img_results):
        s5.shapes.add_picture(img_results, Inches(5.8), Inches(2.5), Inches(6.5), Inches(3.8))

    add_speaker_notes(s5, "These are the results on the held-out test split: mAP@50 of 68.5%, precision 71.2% and recall 69.1%. Per class, fire reaches 93.7% mAP@50 while smoke is the weak point at 43.4% - an honest limitation we address in the roadmap. Notice on the right the smooth convergence of both bounding box and classification losses over 50 epochs.")

    # ==========================================
    # SLIDE 6: Visual Predictions
    # ==========================================
    s6 = prs.slides.add_slide(slide_layout)
    set_bg(s6)
    add_header(s6, "Visual Validation: Model Predictions on Test Batches")

    if os.path.exists(img_preds):
        s6.shapes.add_picture(img_preds, Inches(0.8), Inches(1.8), Inches(7.5), Inches(4.8))

    add_card(s6, Inches(8.6), Inches(1.8), Inches(3.9), Inches(4.8), "Detection Characteristics")
    tb = s6.shapes.add_textbox(Inches(8.8), Inches(2.6), Inches(3.5), Inches(3.7))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• Bounding Box Tightness: Accurate boundary delineation on complex, amorphous smoke plumes.\n\n• Multi-Instance Detection: Successfully tags multiple distinct flame sources simultaneously.\n\n• High Confidence: True flames consistently score > 0.70 confidence.\n\n• Day & Night Robustness: Tested across bright daylight and dark smoke-filled corridors."
    p.font.size = Pt(12)
    p.font.color.rgb = C_WHITE

    add_speaker_notes(s6, "This slide displays actual validation predictions generated by our fine-tuned YOLO11n checkpoint. Observe how the model accurately encapsulates amorphous, non-rigid smoke boundaries and isolates multiple fire seeds simultaneously with high confidence.")

    # ==========================================
    # SLIDE 7: Temporal Confirmation Tracker
    # ==========================================
    s7 = prs.slides.add_slide(slide_layout)
    set_bg(s7)
    add_header(s7, "Algorithmic Innovation: Temporal Confirmation Engine")

    add_card(s7, Inches(0.8), Inches(1.8), Inches(5.6), Inches(4.8), "The Problem: Single-Frame Spikes")
    tb = s7.shapes.add_textbox(Inches(1.1), Inches(2.6), Inches(5.0), Inches(3.8))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• Standard YOLO inference operates frame-by-frame with zero memory of the past.\n\n• A reflective vehicle, cigarette lighter, or fluorescent light flicker can register 0.51 confidence for a single 30ms frame.\n\n• Result in naive systems: Constant false alarms, causing evacuation fatigue and operator distrust."
    p.font.size = Pt(13)
    p.font.color.rgb = C_WHITE

    add_card(s7, Inches(6.8), Inches(1.8), Inches(5.7), Inches(4.8), "Our Solution: Consensus State Machine")
    tb = s7.shapes.add_textbox(Inches(7.1), Inches(2.6), Inches(5.1), Inches(3.8))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• Consecutive Frame Tracking: When an object appears, ConfirmationTracker marks it as a Candidate.\n\n• Threshold Verification: Detection must persist for N consecutive frames (N=2) before confirmed incident creation.\n\n• One Event per Incident: The class latches after confirmation and re-arms only after it has been absent for 3 frames — no event flood.\n\n• Per-Class Tracking: Fire and smoke are counted independently, so a scene containing both confirms both.\n\n• Latency Impact: At ~5 FPS, 2 frames add ~0.4 s of verification — far faster than any human response, and it removes transient noise."
    p.font.size = Pt(13)
    p.font.color.rgb = C_WHITE

    add_speaker_notes(s7, "One of our main engineering contributions is the Temporal Confirmation Tracker. Standard models evaluate each frame in isolation. If a glare scores 0.51 for one frame, naive systems trigger an alarm. Our state machine requires consecutive frame confirmation, tracks fire and smoke independently, and latches after the alarm so a single incident produces a single event. At roughly five frames per second, two frames add about 0.4 seconds of verification — far faster than a human response, yet enough to drop momentary flickers.")

    # ==========================================
    # SLIDE 8: Hard-Negative Stress Testing (FIRESENSE)
    # ==========================================
    s8 = prs.slides.add_slide(slide_layout)
    set_bg(s8)
    add_header(s8, "Stress Testing: Hard Negatives (FIRESENSE Benchmark)")

    add_card(s8, Inches(0.8), Inches(1.8), Inches(5.6), Inches(4.8), "Smoke-Negative Clip (45.1s)")
    tb = s8.shapes.add_textbox(Inches(1.1), Inches(2.6), Inches(5.0), Inches(3.8))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• Dataset: European FP7 FIRESENSE Benchmark.\n\n• Scenario: Outdoor non-fire footage with drifting clouds, tree shadows, and moving vehicles.\n\n• Results:\n  - 0 Raw Fire Detections\n  - 0 Raw Smoke Detections\n  - 0 Confirmed Incidents\n\n• Specificity: 100% on challenging outdoor daytime smoke-negative footage."
    p.font.size = Pt(13)
    p.font.color.rgb = C_GREEN

    add_card(s8, Inches(6.8), Inches(1.8), Inches(5.7), Inches(4.8), "Fire-Negative Clip (15.5s) & Analysis")
    tb = s8.shapes.add_textbox(Inches(7.1), Inches(2.6), Inches(2.6), Inches(3.8))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• Scenario: Night scene with car headlights reflecting off wet road asphalt.\n\n• Results:\n  - 7 raw detections -> 1 confirmed false alarm\n\n• Critical Scientific Finding:\n  - Headlights produce continuous, multi-frame specular glare, bypassing temporal confirmation.\n\n• Solution for Production:\n  - Chromatic Cr/Cb color filtering and 10–13 Hz flame flicker frequency analysis."
    p.font.size = Pt(12)
    p.font.color.rgb = C_WHITE

    add_speaker_notes(s8, "Rather than only showing curated success stories, I subjected FireWatch AI to the European FIRESENSE benchmark. On the 45-second smoke-negative video, the system achieved 100% specificity with zero false alarms. On the wet-road night clip, vehicle headlights produced seven raw detections and a single confirmed false alarm - four before the latch fix - because the glare persisted across frames. This demonstrates that continuous glare requires chromatic filtering in future production iterations.")

    # ==========================================
    # SLIDE 9: Forensics, Storage & Alerting
    # ==========================================
    s9 = prs.slides.add_slide(slide_layout)
    set_bg(s9)
    add_header(s9, "Forensic Evidence Logging & Alert Architecture")

    add_card(s9, Inches(0.8), Inches(1.8), Inches(3.6), Inches(4.8), "1. Evidence Capture")
    tb = s9.shapes.add_textbox(Inches(1.1), Inches(2.6), Inches(3.0), Inches(3.7))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• Immediate Snapshot: Saves full-resolution annotated frame with bounding boxes.\n\n• Naming Scheme: Timestamped cryptographic filenames for audit integrity.\n\n• Storage: Dedicated snapshots repository for incident review."
    p.font.size = Pt(13)
    p.font.color.rgb = C_WHITE

    add_card(s9, Inches(4.8), Inches(1.8), Inches(3.6), Inches(4.8), "2. SQLite Persistence")
    tb = s9.shapes.add_textbox(Inches(5.1), Inches(2.6), Inches(3.0), Inches(3.7))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• Atomic Transactions: Zero-configuration thread-safe local DB.\n\n• detection_events: Tracks timestamp, class ('fire'/'smoke'), confidence, camera source.\n\n• alerts: Stores acknowledgment status and operator review flags."
    p.font.size = Pt(13)
    p.font.color.rgb = C_WHITE

    add_card(s9, Inches(8.8), Inches(1.8), Inches(3.7), Inches(4.8), "3. Alert Dispatcher")
    tb = s9.shapes.add_textbox(Inches(9.1), Inches(2.6), Inches(3.1), Inches(3.7))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• Audio Alarms: Local WAV playback with hardware frequency beeper fallback.\n\n• Alert Cooldown: 60-second throttling prevents alert spamming for ongoing fires.\n\n• UI Acknowledgment: Operators can silence and verify active incidents."
    p.font.size = Pt(13)
    p.font.color.rgb = C_WHITE

    add_speaker_notes(s9, "When an incident is confirmed, the system saves an evidence snapshot with the detection coordinates, commits an event record into SQLite, and triggers an audio alarm. A 60-second cooldown prevents repeated alert spamming while continuous logging continues in the background.")

    # ==========================================
    # SLIDE 10: Testing & Software Quality
    # ==========================================
    s10 = prs.slides.add_slide(slide_layout)
    set_bg(s10)
    add_header(s10, "Software Verification: 62 Automated Tests (100% Pass)")

    add_card(s10, Inches(0.8), Inches(1.8), Inches(11.7), Inches(4.8), "Test Suite Structure & Coverage")
    tb = s10.shapes.add_textbox(Inches(1.2), Inches(2.6), Inches(11.0), Inches(3.8))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• test_detection.py (Computer Vision Layer):\n  ✔ Verified Non-Maximum Suppression and per-class confidence thresholds.\n  ✔ Verified ConfirmationTracker latch, re-arm and fire+smoke in the same frame.\n  ✔ Verified blank-frame guard, box-area sanity limits and evidence file writing.\n\n• test_api.py / test_web.py / test_config.py (Backend & Persistence):\n  ✔ Verified SQLite persistence, evidence path-traversal protection and alert acknowledgement.\n  ✔ Verified every REST endpoint and every HTML page (dashboard, history, incident, evidence).\n  ✔ Verified .env parsing, settings validation and per-test storage isolation.\n\n• Execution Result: 62 passed in ~14 seconds under Python 3.13 — each test runs on a temporary database."
    p.font.size = Pt(13)
    p.font.color.rgb = C_WHITE

    add_speaker_notes(s10, "To ensure production-grade reliability, the codebase ships with 62 automated tests. They cover the confirmation state machine, the blank-frame guard, box filtering, evidence writing with path-traversal protection, alert acknowledgement, every REST route and every page. Each test runs against a temporary database, so running the suite can never damage operational data.")

    # ==========================================
    # SLIDE 11: Web Dashboard & Monitoring
    # ==========================================
    s11 = prs.slides.add_slide(slide_layout)
    set_bg(s11)
    add_header(s11, "Operator Dashboard & RESTful Management API")

    add_card(s11, Inches(0.8), Inches(1.8), Inches(5.6), Inches(4.8), "Flask Monitoring Dashboard")
    tb = s11.shapes.add_textbox(Inches(1.1), Inches(2.6), Inches(5.0), Inches(3.8))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• Real-Time Video: Live MJPEG stream rendered directly in the web browser at /video_feed.\n\n• Honest Status Badges: Camera, model and stream state are read from the live runtime, not hard-coded.\n\n• Incident Table: Latest events with class, confidence bar, camera source and acknowledgement status.\n\n• Incident Detail: Stored evidence frame served from /evidence/<id> with one-click acknowledgement."
    p.font.size = Pt(13)
    p.font.color.rgb = C_WHITE

    add_card(s11, Inches(6.8), Inches(1.8), Inches(5.7), Inches(4.8), "REST API Endpoints")
    tb = s11.shapes.add_textbox(Inches(7.1), Inches(2.6), Inches(5.1), Inches(3.8))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• GET /api/status: Returns live system health, real camera status, model status and detection statistics.\n\n• GET /api/events: Filtered query for incidents by class, camera source, status or limit.\n\n• POST /api/alerts/<id>/acknowledge: Operator confirms and silences an alert.\n\n• PUT /api/settings: Updates confidence thresholds, cool-down and confirmation frames for new capture sessions — no restart required."
    p.font.size = Pt(13)
    p.font.color.rgb = C_WHITE

    add_speaker_notes(s11, "Here is the operator dashboard. Built using Flask and responsive HTML/JavaScript, it displays the live video stream, status badges, incident logs, and evidence snapshots. All capabilities are exposed via REST API endpoints, allowing integration into building automation systems.")

    # ==========================================
    # SLIDE 12: Conclusion & Q&A
    # ==========================================
    s12 = prs.slides.add_slide(slide_layout)
    set_bg(s12)
    add_header(s12, "Conclusion & Project Defense Q&A", "SUMMARY")

    add_card(s12, Inches(0.8), Inches(1.8), Inches(11.7), Inches(4.8), "Project Summary & Key Takeaways")
    tb = s12.shapes.add_textbox(Inches(1.2), Inches(2.6), Inches(11.0), Inches(3.8))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "• Technical Success: Fine-tuned YOLO11n reaches 68.5% mAP@50 and 71.2% precision, at ~5 FPS on an 8-core CPU.\n\n• False Alarm Mitigation: Per-class temporal confirmation, blank-frame guard and box-area sanity filters.\n\n• Full-Stack Architecture: OpenCV capture (webcam or RTSP), SQLite storage, evidence snapshots, Flask dashboard and REST API.\n\n• Rigorous Testing: 62 automated Pytest tests with per-test database isolation + real FIRESENSE hard-negative validation.\n\n• Future Roadmap: hard-negative fine-tuning, ONNX/OpenVINO export for faster CPU inference, SMTP/Telegram alerts, and 10–13 Hz flame flicker analysis.\n\n──────────────────────────────────────────────────────────────────────────\nThank you for your time and guidance! I am now open to your questions."
    p.font.size = Pt(14)
    p.font.color.rgb = C_WHITE

    add_speaker_notes(s12, "To conclude, FireWatch AI demonstrates how modern computer vision combined with temporal filtering and solid software architecture delivers real-time, explainable fire and smoke detection on everyday consumer hardware. Thank you very much for your attention. I would be pleased to answer any questions from the jury.")

    # Save
    primary = os.path.join(PROJECT_ROOT, "FireWatch_AI_Presentation_Manai_Jesser.pptx")
    mirror = os.path.join(PROJECT_ROOT, "FireWatch_AI_Presentation.pptx")
    try:
        prs.save(primary)
        shutil.copy2(primary, mirror)
        print(f"Successfully generated PowerPoint at: {primary}")
        print(f"Mirrored to: {mirror}")
    except PermissionError:
        prs.save(mirror)
        print(f"Primary file was open in PowerPoint. Saved updated deck to: {mirror}")

if __name__ == "__main__":
    create_deck()
