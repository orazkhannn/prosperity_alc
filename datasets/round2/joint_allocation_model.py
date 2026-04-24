from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from speed_optimizer import (
    DiscreteSpeedDistribution,
    OptimizationResult,
    optimize_parameters_from_distribution,
)


HEURISTIC_TEMPLATES = np.array(
    [
        [10, 50, 40],
        [15, 45, 40],
        [20, 40, 40],
        [20, 50, 30],
        [10, 40, 50],
        [25, 35, 40],
        [20, 30, 50],
        [30, 40, 30],
        [15, 35, 50],
        [25, 45, 30],
        [20, 45, 35],
        [5, 55, 40],
        [15, 50, 35],
        [10, 45, 45],
        [20, 35, 45],
        [25, 40, 35],
    ],
    dtype=int,
)
HEURISTIC_TEMPLATE_PROBABILITIES = np.array(
    [
        0.10,
        0.11,
        0.08,
        0.09,
        0.08,
        0.08,
        0.07,
        0.06,
        0.05,
        0.05,
        0.05,
        0.05,
        0.05,
        0.04,
        0.03,
        0.01,
    ],
    dtype=float,
)
HEURISTIC_TEMPLATE_PROBABILITIES /= HEURISTIC_TEMPLATE_PROBABILITIES.sum()

OPTIMIZER_OFFSETS = np.array(
    [
        [0, 0, 0],
        [-2, 2, 0],
        [2, -2, 0],
        [0, 2, -2],
        [0, -2, 2],
        [-5, 5, 0],
        [5, -5, 0],
        [-3, 3, 0],
        [3, -3, 0],
        [-4, 2, 2],
        [4, -2, -2],
    ],
    dtype=int,
)
OPTIMIZER_OFFSET_PROBABILITIES = np.array(
    [0.18, 0.10, 0.10, 0.10, 0.10, 0.08, 0.08, 0.08, 0.08, 0.05, 0.05],
    dtype=float,
)
OPTIMIZER_OFFSET_PROBABILITIES /= OPTIMIZER_OFFSET_PROBABILITIES.sum()

COPYCAT_OFFSETS = np.array(
    [
        [0, 0, 0],
        [-5, 5, 0],
        [5, -5, 0],
        [0, 5, -5],
        [0, -5, 5],
        [-5, 0, 5],
        [5, 0, -5],
    ],
    dtype=int,
)
COPYCAT_OFFSET_PROBABILITIES = np.array(
    [0.30, 0.16, 0.16, 0.12, 0.12, 0.07, 0.07],
    dtype=float,
)
COPYCAT_OFFSET_PROBABILITIES /= COPYCAT_OFFSET_PROBABILITIES.sum()


@dataclass(frozen=True)
class JointPopulationConfig:
    n_population_samples: int = 200_000
    n_nonstrategic_samples: int = 200_000
    n_opponents: int = 19_999
    step: float = 1.0
    seed: int | None = 7
    random_share: float = 0.50
    heuristic_share: float = 0.325
    optimizer_share: float = 0.10
    copycat_share: float = 0.075
    random_dirichlet_alpha: tuple[float, float, float] = (1.0, 1.4, 1.3)
    max_fixed_point_iterations: int = 4

    def type_shares(self) -> dict[str, float]:
        return {
            "random": self.random_share,
            "heuristic": self.heuristic_share,
            "optimizer": self.optimizer_share,
            "copycat": self.copycat_share,
        }


@dataclass(frozen=True)
class JointPopulationResult:
    config: JointPopulationConfig
    allocation_samples: np.ndarray
    type_counts: dict[str, int]
    nonstrategic_best_response: OptimizationResult
    population_best_response: OptimizationResult
    optimizer_center: tuple[int, int, int]
    copycat_center: tuple[int, int, int]
    fixed_point_iterations: int
    speed_distribution: DiscreteSpeedDistribution

    def realized_type_shares(self) -> dict[str, float]:
        total = float(sum(self.type_counts.values()))
        return {
            name: count / total
            for name, count in self.type_counts.items()
        }


def probability_at(distribution: DiscreteSpeedDistribution, c: int) -> float:
    return float(np.sum(distribution.probabilities[distribution.values == c]))


def top_speed_levels(
    distribution: DiscreteSpeedDistribution,
    top_n: int = 10,
) -> list[tuple[int, float]]:
    order = np.argsort(distribution.probabilities)[::-1][:top_n]
    return [
        (int(distribution.values[idx]), float(distribution.probabilities[idx]))
        for idx in order
    ]


def build_joint_population_model(
    config: JointPopulationConfig = JointPopulationConfig(),
) -> JointPopulationResult:
    _validate_config(config)

    nonstrategic_rng = np.random.default_rng(config.seed)
    nonstrategic_allocations = _sample_nonstrategic_allocations(
        rng=nonstrategic_rng,
        total_samples=config.n_nonstrategic_samples,
        config=config,
    )
    nonstrategic_distribution = DiscreteSpeedDistribution.from_samples(
        nonstrategic_allocations[:, 2]
    )
    nonstrategic_best_response = optimize_parameters_from_distribution(
        distribution=nonstrategic_distribution,
        n_opponents=config.n_opponents,
        step=config.step,
    )

    optimizer_center = (
        int(nonstrategic_best_response.a),
        int(nonstrategic_best_response.b),
        int(nonstrategic_best_response.c),
    )
    fixed_point_iterations = 0
    final_allocations = None
    final_counts = None
    final_copycat_center = None
    final_distribution = None
    final_best_response = None

    for iteration in range(config.max_fixed_point_iterations):
        population_rng = np.random.default_rng(_offset_seed(config.seed, iteration + 1))
        final_allocations, final_counts, final_copycat_center = _sample_population_allocations(
            rng=population_rng,
            total_samples=config.n_population_samples,
            config=config,
            optimizer_center=optimizer_center,
        )
        final_distribution = DiscreteSpeedDistribution.from_samples(final_allocations[:, 2])
        final_best_response = optimize_parameters_from_distribution(
            distribution=final_distribution,
            n_opponents=config.n_opponents,
            step=config.step,
        )
        next_center = (
            int(final_best_response.a),
            int(final_best_response.b),
            int(final_best_response.c),
        )
        fixed_point_iterations = iteration + 1
        if next_center == optimizer_center:
            break
        optimizer_center = next_center

    if (
        final_allocations is None
        or final_counts is None
        or final_copycat_center is None
        or final_distribution is None
        or final_best_response is None
    ):
        raise RuntimeError("joint population model failed to generate a final result")

    return JointPopulationResult(
        config=config,
        allocation_samples=final_allocations,
        type_counts=final_counts,
        nonstrategic_best_response=nonstrategic_best_response,
        population_best_response=final_best_response,
        optimizer_center=optimizer_center,
        copycat_center=final_copycat_center,
        fixed_point_iterations=fixed_point_iterations,
        speed_distribution=final_distribution,
    )


def _validate_config(config: JointPopulationConfig) -> None:
    if config.n_population_samples <= 0:
        raise ValueError("n_population_samples must be positive")
    if config.n_nonstrategic_samples <= 0:
        raise ValueError("n_nonstrategic_samples must be positive")
    if config.n_opponents < 0:
        raise ValueError("n_opponents must be non-negative")
    if config.step <= 0:
        raise ValueError("step must be positive")
    if config.max_fixed_point_iterations <= 0:
        raise ValueError("max_fixed_point_iterations must be positive")

    shares = config.type_shares()
    if any(share < 0 for share in shares.values()):
        raise ValueError("type shares must be non-negative")
    if not np.isclose(sum(shares.values()), 1.0):
        raise ValueError("type shares must sum to 1")


def _sample_nonstrategic_allocations(
    rng: np.random.Generator,
    total_samples: int,
    config: JointPopulationConfig,
) -> np.ndarray:
    shares = np.array([config.random_share, config.heuristic_share], dtype=float)
    shares /= shares.sum()
    random_count, heuristic_count = _counts_from_shares(total_samples, shares)
    return np.concatenate(
        [
            _sample_random_allocations(
                rng=rng,
                n=random_count,
                alpha=config.random_dirichlet_alpha,
            ),
            _sample_from_templates(
                rng=rng,
                n=heuristic_count,
                templates=HEURISTIC_TEMPLATES,
                probabilities=HEURISTIC_TEMPLATE_PROBABILITIES,
            ),
        ],
        axis=0,
    )


def _sample_population_allocations(
    rng: np.random.Generator,
    total_samples: int,
    config: JointPopulationConfig,
    optimizer_center: tuple[int, int, int],
) -> tuple[np.ndarray, dict[str, int], tuple[int, int, int]]:
    shares = np.fromiter(config.type_shares().values(), dtype=float)
    counts = _counts_from_shares(total_samples, shares)
    type_names = list(config.type_shares().keys())
    type_counts = dict(zip(type_names, counts, strict=True))

    copycat_center = _round_center_to_grid(optimizer_center, grid=5)
    allocations = np.concatenate(
        [
            _sample_random_allocations(
                rng=rng,
                n=type_counts["random"],
                alpha=config.random_dirichlet_alpha,
            ),
            _sample_from_templates(
                rng=rng,
                n=type_counts["heuristic"],
                templates=HEURISTIC_TEMPLATES,
                probabilities=HEURISTIC_TEMPLATE_PROBABILITIES,
            ),
            _sample_centered_offsets(
                rng=rng,
                n=type_counts["optimizer"],
                center=optimizer_center,
                offsets=OPTIMIZER_OFFSETS,
                probabilities=OPTIMIZER_OFFSET_PROBABILITIES,
            ),
            _sample_centered_offsets(
                rng=rng,
                n=type_counts["copycat"],
                center=copycat_center,
                offsets=COPYCAT_OFFSETS,
                probabilities=COPYCAT_OFFSET_PROBABILITIES,
            ),
        ],
        axis=0,
    )
    return allocations, type_counts, copycat_center


def _sample_random_allocations(
    rng: np.random.Generator,
    n: int,
    alpha: tuple[float, float, float],
) -> np.ndarray:
    weights = rng.dirichlet(alpha, size=n)
    return _simplex_to_integer_allocations(weights, total=100)


def _sample_from_templates(
    rng: np.random.Generator,
    n: int,
    templates: np.ndarray,
    probabilities: np.ndarray,
) -> np.ndarray:
    indices = rng.choice(len(templates), size=n, p=probabilities)
    return templates[indices].copy()


def _sample_centered_offsets(
    rng: np.random.Generator,
    n: int,
    center: tuple[int, int, int],
    offsets: np.ndarray,
    probabilities: np.ndarray,
) -> np.ndarray:
    sampled = np.asarray(center, dtype=int) + offsets[
        rng.choice(len(offsets), size=n, p=probabilities)
    ]
    if np.any(sampled < 0) or np.any(sampled.sum(axis=1) != 100):
        raise ValueError("centered offsets produced invalid allocations")
    return sampled


def _simplex_to_integer_allocations(weights: np.ndarray, total: int) -> np.ndarray:
    scaled = weights / weights.sum(axis=1, keepdims=True) * total
    base = np.floor(scaled).astype(int)
    remainder = total - base.sum(axis=1)
    fractions = scaled - base
    order = np.argsort(-fractions, axis=1)

    rows = np.arange(weights.shape[0])
    for offset_index in range(weights.shape[1]):
        mask = remainder > offset_index
        if not np.any(mask):
            break
        base[rows[mask], order[mask, offset_index]] += 1
    return base


def _round_center_to_grid(
    center: tuple[int, int, int],
    grid: int,
) -> tuple[int, int, int]:
    a = int(grid * round(center[0] / grid))
    b = int(grid * round(center[1] / grid))
    c = 100 - a - b
    if c < 0:
        b += c
        c = 0
    return (a, b, c)


def _counts_from_shares(total: int, shares: np.ndarray) -> list[int]:
    raw = total * shares
    counts = np.floor(raw).astype(int)
    remainder = total - int(counts.sum())
    if remainder > 0:
        order = np.argsort(raw - counts)[::-1]
        counts[order[:remainder]] += 1
    return counts.tolist()


def _offset_seed(seed: int | None, offset: int) -> int | None:
    if seed is None:
        return None
    return seed + offset
