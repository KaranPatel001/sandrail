from throttle import TokenBucket


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_idle_does_not_exceed_capacity():
    clock = FakeClock()
    bucket = TokenBucket(5, 1.0, clock=clock)
    for _ in range(5):
        bucket.try_acquire()
    clock.now = 100.0
    assert sum(bucket.try_acquire() for _ in range(50)) == 5


def test_full_bucket_stays_full():
    clock = FakeClock()
    bucket = TokenBucket(2, 10.0, clock=clock)
    clock.now = 60.0
    assert sum(bucket.try_acquire() for _ in range(10)) == 2


def test_partial_refill_unchanged():
    clock = FakeClock()
    bucket = TokenBucket(10, 2.0, clock=clock)
    bucket.try_acquire(10)
    clock.now = 1.5
    assert sum(bucket.try_acquire() for _ in range(10)) == 3
