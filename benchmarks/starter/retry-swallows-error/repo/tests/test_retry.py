from retrying import retry


def test_returns_value_on_success():
    @retry(times=3)
    def ok():
        return 42

    assert ok() == 42


def test_succeeds_after_failures():
    calls = []

    @retry(times=3)
    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("not yet")
        return "done"

    assert flaky() == "done"
    assert len(calls) == 3
