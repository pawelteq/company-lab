"""RQ worker entry point for Company Lab background tasks.

Usage::

    python -m backend.worker

The worker connects to the Redis instance configured via ``REDIS_URL``
(default ``redis://127.0.0.1:6379/0``) and processes jobs on the
``company-lab`` queue.
"""
from __future__ import annotations

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


QUEUE_NAME = "company-lab"


def main() -> None:
    try:
        import redis as _redis_lib
        from rq import Worker, Queue, SimpleWorker
    except ImportError as exc:
        logger.error("Brakujące zależności: %s.  Zainstaluj redis i rq.", exc)
        sys.exit(1)

    from backend.cache import redis_url

    url = redis_url()
    logger.info("Łączę z Redis: %s", url)

    try:
        conn = _redis_lib.Redis.from_url(url, socket_connect_timeout=5, protocol=2)
        conn.ping()
    except Exception as exc:
        logger.error("Nie mogę połączyć się z Redis: %s", exc)
        sys.exit(1)

    queue = Queue(QUEUE_NAME, connection=conn)
    worker_cls = SimpleWorker if sys.platform == "win32" else Worker
    worker = worker_cls([queue], connection=conn, name="company-lab-worker")

    logger.info("Worker uruchomiony (%s).  Kolejka: %s", worker_cls.__name__, QUEUE_NAME)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
