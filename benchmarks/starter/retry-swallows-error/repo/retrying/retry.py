import functools
import time
from typing import Any, Callable


def retry(
    times: int = 3,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    delay: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
):
    """Retry the decorated function up to ``times`` attempts in total.

    Only exceptions in ``exceptions`` trigger a retry. If every attempt fails,
    the last exception is re-raised. ``sleep(delay)`` is called between
    attempts when ``delay`` is positive.
    """
    if times < 1:
        raise ValueError("times must be at least 1")

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(1, times + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions:
                    if attempt < times and delay > 0:
                        sleep(delay)
            return None

        return wrapper

    return decorator
