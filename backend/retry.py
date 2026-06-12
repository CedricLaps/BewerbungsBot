"""Retry-Dekorator mit exponentiellem Backoff."""
from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")

logger = logging.getLogger(__name__)


def retry(
    attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Wiederholt den Aufruf bei den angegebenen Exceptions bis zu `attempts` Mal."""
    if attempts < 1:
        raise ValueError("attempts muss >= 1 sein")

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            wait = delay
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == attempts:
                        raise
                    logger.warning(
                        "%s fehlgeschlagen (Versuch %d/%d): %s — neuer Versuch in %.1fs",
                        func.__qualname__, attempt, attempts, exc, wait,
                    )
                    time.sleep(wait)
                    wait *= backoff
            raise RuntimeError("unreachable")  # pragma: no cover

        return wrapper

    return decorator
