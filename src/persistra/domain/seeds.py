"""Partition-independent deterministic seed allocation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import ClassVar, cast

from persistra.domain.serialization import canonical_bytes


@dataclass(frozen=True, slots=True)
class SeedSpec:
    """Root for named SHA-256 counter streams."""

    root: int

    GENERATOR: ClassVar[str] = "persistra.seed.sha256_counter@1"

    def __post_init__(self) -> None:
        raw_root = cast("object", self.root)
        if not isinstance(raw_root, int) or isinstance(raw_root, bool):
            raise ValueError("seed root must be an unsigned 64-bit integer")
        if not 0 <= raw_root < 2**64:
            raise ValueError("seed root must be an unsigned 64-bit integer")

    def draw(self, *labels: str, counter: int = 0) -> int:
        """Return one unsigned 64-bit draw from a stable named stream."""
        if not labels or any(not label for label in labels):
            raise ValueError("seed streams require nonempty ordered text labels")
        if isinstance(counter, bool) or not 0 <= counter < 2**64:
            raise ValueError("seed counter must be an unsigned 64-bit integer")
        digest = hashlib.sha256(canonical_bytes([self.root, *labels, counter])).digest()
        return int.from_bytes(digest[:8], "big")
