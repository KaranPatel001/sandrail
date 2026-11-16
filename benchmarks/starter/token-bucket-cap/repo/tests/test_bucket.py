from throttle import TokenBucket


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_initial_burst():
    clock = FakeClock()
    bucket = TokenBucket(3, 1.0, clock=clock)
    assert [bucket.try_acquire() for _ in range(4)] == [True, True, True, False]


def test_refills_over_time():
    clock = FakeClock()
    bucket = TokenBucket(2, 1.0, clock=clock)
    bucket.try_acquire(2)
    clock.now = 1.0
    assert bucket.try_acquire()
    assert not bucket.try_acquire()
