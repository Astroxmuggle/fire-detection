"""Owns the inference workers, one per camera."""

from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, List, Optional

from adapters.model.base import ModelAdapter
from adapters.video.base import VideoSource
from services.camera_registry import Camera
from workers.inference_worker import InferenceWorker, WorkerConfig, WorkerState

logger = logging.getLogger("firewatch.workers")


def _default_adapter_factory(model_path=None, confidence_threshold=None) -> ModelAdapter:
    from adapters.model.yolo import YoloModelAdapter

    return YoloModelAdapter(model_path, confidence_threshold)


def _default_source_factory(camera: Camera) -> VideoSource:
    from adapters.video.opencv import OpenCVVideoSource

    return OpenCVVideoSource(camera.source)


class CameraWorkerManager:
    """Create, track and stop one worker per camera.

    Factories are injectable so tests can run the real worker with a stub model
    and a stub source, and so the application can keep its OpenCV opener
    replaceable.
    """

    def __init__(
        self,
        adapter_factory: Optional[Callable[..., ModelAdapter]] = None,
        source_factory: Optional[Callable[[Camera], VideoSource]] = None,
        config_factory: Optional[Callable[[], WorkerConfig]] = None,
    ):
        self._lock = threading.RLock()
        self._workers: Dict[int, InferenceWorker] = {}
        self._adapter_factory = adapter_factory or _default_adapter_factory
        self._source_factory = source_factory or _default_source_factory
        self._config_factory = config_factory or WorkerConfig.from_settings

    def ensure(
        self,
        camera: Camera,
        model_path: Optional[str] = None,
        confidence_threshold: Optional[float] = None,
    ) -> InferenceWorker:
        """Return a running worker for *camera*, creating one when needed."""
        with self._lock:
            worker = self._workers.get(camera.id)
            if worker is not None and worker.is_alive():
                return worker

            adapter = self._adapter_factory(model_path, confidence_threshold)
            source = self._source_factory(camera)
            worker = InferenceWorker(
                camera_id=camera.id,
                name=camera.name,
                source=source,
                adapter=adapter,
                config=self._config_factory(),
            )
            try:
                worker.start()
            except Exception:
                try:
                    adapter.close()
                except Exception:  # noqa: BLE001 - best effort
                    pass
                raise

            self._workers[camera.id] = worker
            return worker

    def get(self, camera_id) -> Optional[InferenceWorker]:
        with self._lock:
            return self._workers.get(int(camera_id))

    def is_monitoring(self, camera_id=None) -> bool:
        with self._lock:
            if camera_id is None:
                return any(worker.is_alive() for worker in self._workers.values())
            worker = self._workers.get(int(camera_id))
            return worker is not None and worker.is_alive()

    def stop(self, camera_id) -> bool:
        with self._lock:
            worker = self._workers.pop(int(camera_id), None)
        if worker is None:
            return False
        worker.stop()
        return True

    def stop_all(self) -> int:
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()

        stopped = 0
        for worker in workers:
            try:
                if worker.stop():
                    stopped += 1
            except Exception:  # noqa: BLE001 - shutdown must not raise
                logger.exception("failed to stop worker %s", worker.camera_id)
        return stopped

    def status(self) -> List[dict]:
        with self._lock:
            workers = list(self._workers.values())

        payload = []
        for worker in workers:
            stats = worker.stats()
            payload.append({
                "camera_id": worker.camera_id,
                "name": worker.name,
                "source": worker.source.info().raw,
                "state": stats.get("state", WorkerState.STOPPED.value),
                **{key: value for key, value in stats.items() if key != "state"},
            })
        payload.sort(key=lambda item: item["camera_id"])
        return payload
