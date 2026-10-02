from dataclasses import dataclass, field


@dataclass(slots=True)
class TokenBucket:
    capacity: int
    refill_per_second: float
    tokens: float = field(init=False)
    updated_at: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self.tokens = float(self.capacity)

    def allow(self, now: float) -> bool:
        if self.updated_at:
            elapsed = max(now - self.updated_at, 0.0)
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        self.updated_at = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True
