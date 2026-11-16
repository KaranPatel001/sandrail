import pytest

from retrying import retry


def test_last_exception_propagates():
    calls = []

    @retry(times=3, exceptions=(ConnectionError,))
    def fetch():
        calls.append(1)
        raise ConnectionError(f"down {len(calls)}")

    with pytest.raises(ConnectionError, match="down 3"):
        fetch()
    assert len(calls) == 3


def test_unlisted_exception_not_retried():
    calls = []

    @retry(times=5, exceptions=(ConnectionError,))
    def broken():
        calls.append(1)
        raise KeyError("x")

    with pytest.raises(KeyError):
        broken()
    assert len(calls) == 1


def test_sleep_only_between_attempts():
    sleeps = []

    @retry(times=4, delay=0.5, sleep=sleeps.append)
    def always_fails():
        raise ValueError("no")

    with pytest.raises(ValueError):
        always_fails()
    assert sleeps == [0.5, 0.5, 0.5]


def test_single_attempt_raises():
    @retry(times=1)
    def once():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        once()
