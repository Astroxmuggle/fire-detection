# FireWatch AI — Final-Year Project Defense Checklist

## 1. Problem statement
- Fire and smoke detection are safety-critical tasks that benefit from automated monitoring.
- A local webcam-based system can support early warning without requiring a dedicated GPU.
- False alarms must be reduced with configurable thresholds and confirmation logic.

## 2. Objectives achieved
- Real-time fire and smoke detection using YOLO on a local webcam stream.
- Raw detection filtering and duplicate suppression.
- Consecutive-frame confirmation before creating a confirmed incident.
- Evidence snapshot saving for events.
- SQLite-backed event history and alert status tracking.
- Local dashboard for monitoring and event review.
- REST API for system and event queries.
- Automated testing for key project behaviors.

## 3. Technical stack used
- Python
- OpenCV
- Ultralytics YOLO
- Flask
- SQLite
- HTML/CSS/JavaScript
- Pytest

## 4. Runtime verification
- Model path is configured to the trained weights outside the project directory.
- Project tests pass with the current app state.
- Use the command below to verify the app remains green:

```powershell
cd "C:\Users\manna_2c83x\fire-detection-ai\firedetec2\fire-detection-ai"
& "C:\Users\manna_2c83x\fire-detection-ai\.venv\Scripts\python.exe" -m pytest -q
```

## 5. Run instructions
```powershell
cd "C:\Users\manna_2c83x\fire-detection-ai\firedetec2\fire-detection-ai"
& "C:\Users\manna_2c83x\fire-detection-ai\.venv\Scripts\Activate.ps1"
python app.py
```

Then open:

```text
http://127.0.0.1:5000/
```

## 6. Safe shutdown
- Press `Ctrl+C` in the Flask terminal.
- Confirm no webcam process remains active.
- Close the terminal after the app stops cleanly.

## 7. Demo flow for final presentation
1. Show the dashboard home page.
2. Explain the model path and detection configuration.
3. Show the live webcam feed.
4. Explain the confirmation logic across multiple frames.
5. Show how a confirmed event is stored to SQLite.
6. Show the evidence snapshot saved to disk.
7. Show the API endpoints returning event and status data.
8. Explain test coverage and limitations.

## 8. Known limitations
- This is not a certified fire alarm system.
- Live performance depends on local hardware and CPU capacity.
- Model accuracy requires real evaluation on a labeled dataset.
- The prototype does not yet include remote email or cloud integrations.

## 9. Future work
- multiple camera support
- email notification provider
- more advanced dashboard filtering
- formal mAP evaluation on test images and videos
- deployment hardening and optional Docker packaging

## 10. Presentation structure
- Title and problem statement
- System architecture
- Model and camera flow
- Dashboard and API demonstration
- Database and event storage design
- Testing strategy and results
- Limitations and future work

## 11. Stronger academic explanation points
- This project combines computer vision, software engineering, backend architecture, database design, testing, and practical system deployment.
- The design is modular and extensible.
- The project demonstrates real engineering discipline through validation and iteration.
