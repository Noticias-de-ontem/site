import unittest


from backend.rate_limit import _MemoryJobSlots, _MemoryRateLimiter


class RateLimitTests(unittest.TestCase):
    def test_memory_rate_limit_blocks_after_limit(self):
        limiter = _MemoryRateLimiter()
        self.assertTrue(limiter.consume("client", 2, 60).allowed)
        self.assertTrue(limiter.consume("client", 2, 60).allowed)
        blocked = limiter.consume("client", 2, 60)
        self.assertFalse(blocked.allowed)
        self.assertGreaterEqual(blocked.retry_after, 1)

    def test_memory_job_slots_are_idempotent(self):
        slots = _MemoryJobSlots()
        self.assertTrue(slots.reserve("job-1", 1, 60))
        self.assertTrue(slots.reserve("job-1", 1, 60))
        self.assertFalse(slots.reserve("job-2", 1, 60))
        slots.release("job-1")
        slots.release("job-1")
        self.assertTrue(slots.reserve("job-2", 1, 60))

if __name__ == "__main__":
    unittest.main()
