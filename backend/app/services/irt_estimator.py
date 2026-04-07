from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List


@dataclass
class IRTItemResult:
    score: float
    difficulty: float
    discrimination: float = 1.0


def estimate_theta(items: List[IRTItemResult]) -> float:
    if not items:
        return 0.0
    theta = 0.0
    for _ in range(10):
        grad = 0.0
        hess = 0.0
        for it in items:
            a = max(0.3, min(2.5, it.discrimination))
            b = max(-3.0, min(3.0, it.difficulty))
            p = 1.0 / (1.0 + math.exp(-a * (theta - b)))
            y = max(0.0, min(1.0, it.score))
            grad += a * (y - p)
            hess -= (a * a) * p * (1 - p)
        if abs(hess) < 1e-6:
            break
        theta_next = theta - (grad / hess)
        if abs(theta_next - theta) < 1e-4:
            theta = theta_next
            break
        theta = theta_next
    return round(max(-3.0, min(3.0, theta)), 4)


def theta_to_level(theta: float) -> int:
    if theta <= -1.0:
        return 0
    if theta <= 0.2:
        return 1
    if theta <= 1.2:
        return 2
    return 3
