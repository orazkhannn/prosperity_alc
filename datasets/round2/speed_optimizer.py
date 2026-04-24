from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


def research(a: float) -> float:
    return 200000 * np.log1p(a) / np.log1p(100)


def scale(b: float) -> float:
    return 7 * b / 100


def budget_used(a: float, b: float, c: float) -> float:
    return 50000 * (a + b + c) / 100


def rank_multiplier(rank: float, population_size: int) -> float:
    if population_size <= 1:
        return 0.9
    return 0.9 - ((rank - 1) / (population_size - 1)) * 0.8


def speed_multiplier(c: float, opponent_speeds: Iterable[float]) -> float:
    opponents = np.asarray(list(opponent_speeds), dtype=float)
    population_size = len(opponents) + 1
    rank = 1 + np.sum(opponents > c)
    return rank_multiplier(rank=rank, population_size=population_size)


@dataclass(frozen=True)
class DiscreteSpeedDistribution:
    values: np.ndarray
    probabilities: np.ndarray

    @classmethod
    def from_pairs(
        cls,
        values: Iterable[float],
        probabilities: Iterable[float],
    ) -> "DiscreteSpeedDistribution":
        values_array = np.asarray(list(values), dtype=float)
        probabilities_array = np.asarray(list(probabilities), dtype=float)

        if values_array.size == 0:
            raise ValueError("values must not be empty")
        if values_array.shape != probabilities_array.shape:
            raise ValueError("values and probabilities must have the same length")
        if np.any(probabilities_array < 0):
            raise ValueError("probabilities must be non-negative")

        total = probabilities_array.sum()
        if total <= 0:
            raise ValueError("probabilities must sum to a positive value")

        return cls(
            values=values_array,
            probabilities=probabilities_array / total,
        )

    @classmethod
    def from_samples(cls, samples: Iterable[float]) -> "DiscreteSpeedDistribution":
        sample_array = np.asarray(list(samples), dtype=float)
        if sample_array.size == 0:
            raise ValueError("samples must not be empty")
        values, counts = np.unique(sample_array, return_counts=True)
        return cls(values=values, probabilities=counts / counts.sum())

    def sample_opponents(
        self,
        n_opponents: int,
        n_trials: int,
        seed: int | None = None,
    ) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return rng.choice(
            self.values,
            size=(n_trials, n_opponents),
            p=self.probabilities,
        )


def expected_speed_from_distribution(
    c: float,
    distribution: DiscreteSpeedDistribution,
    n_opponents: int,
    n_trials: int = 20000,
    seed: int | None = None,
) -> float:
    if n_opponents < 0:
        raise ValueError("n_opponents must be non-negative")

    if n_opponents == 0:
        return 0.9

    # The rank multiplier is linear in rank, so for an i.i.d. discrete
    # distribution we can compute the expectation exactly from the tail mass.
    _ = n_trials, seed  # Kept for backwards-compatible call sites.
    higher_probability = float(np.sum(distribution.probabilities[distribution.values > c]))
    expected_rank = 1 + n_opponents * higher_probability
    return float(rank_multiplier(rank=expected_rank, population_size=n_opponents + 1))


def expected_speed_from_samples(c: float, speed_samples: Iterable[Iterable[float]]) -> float:
    samples = np.asarray(list(speed_samples), dtype=float)
    if samples.ndim != 2 or samples.shape[0] == 0:
        raise ValueError("speed_samples must be a non-empty 2D array-like")
    higher_counts = np.sum(samples > c, axis=1)
    ranks = 1 + higher_counts
    multipliers = rank_multiplier(ranks, samples.shape[1] + 1)
    return float(np.mean(multipliers))


def pnl(a: float, b: float, c: float, expected_speed: float) -> float:
    return research(a) * scale(b) * expected_speed - budget_used(a, b, c)


@dataclass(frozen=True)
class OptimizationResult:
    a: float
    b: float
    c: float
    expected_speed: float
    expected_pnl: float


def optimize_parameters_from_distribution(
    distribution: DiscreteSpeedDistribution,
    n_opponents: int,
    step: float = 1.0,
    n_trials: int = 20000,
    seed: int | None = None,
) -> OptimizationResult:
    if step <= 0:
        raise ValueError("step must be positive")

    grid = np.arange(0.0, 100.0 + step / 2, step)
    speed_cache = {
        float(c): expected_speed_from_distribution(
            c=float(c),
            distribution=distribution,
            n_opponents=n_opponents,
            n_trials=n_trials,
            seed=seed,
        )
        for c in grid
    }

    best_result: OptimizationResult | None = None
    for a in grid:
        for b in grid:
            c = 100.0 - a - b
            if c < -1e-9:
                continue
            c = round(max(c, 0.0) / step) * step
            if c not in speed_cache:
                continue

            expected_speed = speed_cache[c]
            candidate = OptimizationResult(
                a=float(a),
                b=float(b),
                c=float(c),
                expected_speed=float(expected_speed),
                expected_pnl=float(pnl(a, b, c, expected_speed)),
            )
            if best_result is None or candidate.expected_pnl > best_result.expected_pnl:
                best_result = candidate

    if best_result is None:
        raise RuntimeError("no feasible solution found")
    return best_result


def optimize_parameters_from_samples(
    speed_samples: Iterable[Iterable[float]],
    step: float = 1.0,
) -> OptimizationResult:
    if step <= 0:
        raise ValueError("step must be positive")

    sample_array = np.asarray(list(speed_samples), dtype=float)
    if sample_array.ndim != 2 or sample_array.shape[0] == 0:
        raise ValueError("speed_samples must be a non-empty 2D array-like")

    grid = np.arange(0.0, 100.0 + step / 2, step)
    speed_cache = {
        float(c): expected_speed_from_samples(float(c), sample_array)
        for c in grid
    }

    best_result: OptimizationResult | None = None
    for a in grid:
        for b in grid:
            c = 100.0 - a - b
            if c < -1e-9:
                continue
            c = round(max(c, 0.0) / step) * step
            if c not in speed_cache:
                continue

            expected_speed = speed_cache[c]
            candidate = OptimizationResult(
                a=float(a),
                b=float(b),
                c=float(c),
                expected_speed=float(expected_speed),
                expected_pnl=float(pnl(a, b, c, expected_speed)),
            )
            if best_result is None or candidate.expected_pnl > best_result.expected_pnl:
                best_result = candidate

    if best_result is None:
        raise RuntimeError("no feasible solution found")
    return best_result
