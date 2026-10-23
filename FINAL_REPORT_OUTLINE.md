# FireWatch AI — Final Report Outline

## 1. Title
FireWatch AI: Real-Time Fire and Smoke Detection Using YOLO, Flask, and SQLite

## 2. Abstract
A short summary of the project objective, methodology, and outcome. Mention that the system monitors a live camera, confirms repeated detections, saves evidence, and presents data in a local dashboard.

## 3. Problem statement
Explain why fire and smoke monitoring systems are important and why automated detection can reduce human workload and improve response time. Mention the challenge of false positives in local, CPU-based detection systems.

## 4. Objectives and scope
List the major project goals:
- real-time detection
- low false alarm rate
- persistent event logging
- dashboard and API access
- safe local deployment

## 5. Literature and technology rationale
Explain why YOLO, OpenCV, Flask, and SQLite were chosen for this project. Mention CPU compatibility, speed, and local deployment constraints.

## 6. System architecture
Describe the modular architecture:
- camera service
- detection manager
- confirmation tracker
- evidence service
- event service
- alert manager
- database layer
- routes and dashboard

## 7. Methodology
Describe the processing pipeline:
1. read frame from camera
2. run YOLO inference
3. filter by confidence threshold
4. suppress duplicates
5. confirm repeated detections across frames
6. save evidence if confirmed
7. persist event in SQLite
8. update dashboard and API data

## 8. Dataset and model configuration
Describe the available trained model and how it was integrated into the application without retraining. Explain the dataset source and the role of fire and smoke classes.

## 9. Functional requirements
List the implemented functional requirements and the project limitations.

## 10. Non-functional requirements
Discuss reliability, maintainability, performance, safety, and local deployment constraints.

## 11. Results and testing
Summarize the test suite and outcomes:
- detection logic tests
- database tests
- alert tests
- API tests
- integration behavior tests

## 12. Performance discussion
Explain expected local CPU constraints, approximate frame processing behavior, and the importance of confidence thresholds and frame confirmation.

## 13. Limitations and future work
Discuss:
- no certified fire alarm claims
- no emergency service integration
- CPU-only constraints
- future multi-camera support and cloud services

## 14. Conclusion
Summarize what was successfully implemented and what the project demonstrates in terms of applied AI and software engineering.

## 15. References
List relevant papers, YOLO documentation, OpenCV references, and Flask documentation if used.

## 16. Appendix
Include screenshots, sample outputs, and command snippets used during testing and execution.
