"""Model comparison benchmarking for semantic coherence embedding models.

Compares two or more embedding models (e.g. all-MiniLM-L6-v2 vs all-mpnet-base-v2)
on a set of documents, measuring:
  - Score agreement (Pearson r, Spearman rho, MAE)
  - Runtime overhead per document and total
  - Calibration statistics (score distribution shifts)

This is used to determine which model best differentiates clarity in skill
documentation while maintaining computational efficiency.

NOT derived from or vendored from any other project. All code reimplemented
from scratch.
"""

from __future__ import annotations

import time
import json
import math
from dataclasses import dataclass, field
from typing import Any
from collections.abc import Sequence
from pathlib import Path


# ============================================================
# Data classes for comparison results
# ============================================================


@dataclass
class ModelTiming:
    """Timing info for a single model's analysis of one document."""
    model_name: str
    file_path: str | None = None
    elapsed_seconds: float = 0.0


@dataclass
class ScorePair:
    """A pair of coherence scores for the same document from two models."""
    document: str
    model_a_score: float | None
    model_b_score: float | None
    a_clarity: float | None = None
    b_clarity: float | None = None


@dataclass
class ComparisonMetrics:
    """Statistics comparing two coherence scoring models."""
    model_a_name: str
    model_b_name: str
    n_documents: int

    # Correlation metrics
    pearson_r: float = 0.0      # Linear correlation of raw coherence scores
    spearman_rho: float = 0.0   # Rank correlation (monotonic relationship)

    # Agreement on score ordering (which document ranks higher)
    rank_agreement_pct: float = 100.0  # % where both models agree on ordering

    # Absolute agreement
    mean_absolute_error: float = 0.0  # Mean |score_a - score_b|
    mean_squared_error: float = 0.0   # Mean (score_a - score_b)²

    # Score distribution statistics per model
    model_a_mean_coherence: float = 0.0
    model_a_std_coherence: float = 0.0
    model_b_mean_coherence: float = 0.0
    model_b_std_coherence: float = 0.0

    # Runtime overhead
    model_a_avg_time_ms: float = 0.0     # Per-document average (ms)
    model_b_avg_time_ms: float = 0.0     # Per-document average (ms)
    total_runtime_ms: float = 0.0        # Total wall-clock ms
    overhead_ratio: float = 1.0           # model_b / model_a runtime ratio

    # Clarity score agreement: not computed, always None
    pearson_r_clarity: float | None = None


@dataclass
class BenchmarkResult:
    """Full benchmark result for all models tested."""
    n_documents: int
    timings: list[ModelTiming] = field(default_factory=list)
    comparisons: list[ComparisonMetrics] = field(default_factory=list)
    raw_scores: dict[str, list[tuple[str, float]]] = field(default_factory=dict)  # model -> [(doc, score)]

    def to_json(self) -> str:
        """Serialize the benchmark result as JSON."""
        data = {
            "n_documents": self.n_documents,
            "comparisons": [
                {
                    "model_a": m.model_a_name,
                    "model_b": m.model_b_name,
                    "n_documents": m.n_documents,
                    "pearson_r": round(m.pearson_r, 4),
                    "spearman_rho": round(m.spearman_rho, 4),
                    "rank_agreement_pct": round(m.rank_agreement_pct, 1),
                    "mean_absolute_error": round(m.mean_absolute_error, 2),
                    "mean_squared_error": round(m.mean_squared_error, 2),
                    "model_a_mean_coherence": round(m.model_a_mean_coherence, 1),
                    "model_a_std_coherence": round(m.model_a_std_coherence, 1),
                    "model_b_mean_coherence": round(m.model_b_mean_coherence, 1),
                    "model_b_std_coherence": round(m.model_b_std_coherence, 1),
                    "model_a_avg_time_ms": round(m.model_a_avg_time_ms, 1),
                    "model_b_avg_time_ms": round(m.model_b_avg_time_ms, 1),
                    "total_runtime_ms": round(m.total_runtime_ms, 1),
                    "overhead_ratio": round(m.overhead_ratio, 2),
                    "pearson_r_clarity": m.pearson_r_clarity,
                }
                for m in self.comparisons
            ],
            "raw_scores": {
                model: [(doc, round(score, 2)) for doc, score in scores]
                for model, scores in self.raw_scores.items()
            },
        }
        return json.dumps(data, indent=2)


# ============================================================
# Statistical helper functions
# ============================================================


def _pearson(x: Sequence[float], y: Sequence[float]) -> float:
    """Compute Pearson correlation coefficient."""
    n = len(x)
    if n < 2:
        return 0.0

    x_mean = sum(x) / n
    y_mean = sum(y) / n

    cov = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
    var_x = sum((xi - x_mean) ** 2 for xi in x)
    var_y = sum((yi - y_mean) ** 2 for yi in y)

    denom = math.sqrt(var_x * var_y)
    if denom == 0:
        return 0.0

    return cov / denom


def _spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Compute Spearman rank correlation coefficient."""
    n = len(x)
    if n < 2:
        return 0.0

    def rank(values: Sequence[float]) -> list[int]:
        """Tie-breaking average ranking."""
        indexed = sorted(enumerate(values), key=lambda t: t[1])
        ranks = [0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and indexed[j + 1][1] == indexed[j][1]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                ranks[indexed[k][0]] = avg_rank
            i = j + 1
        return ranks

    rank_x = rank(x)
    rank_y = rank(y)

    # Use Pearson on ranks
    return _pearson(rank_x, rank_y)


# ============================================================
# Core comparison logic
# ============================================================


def compare_models_benchmark(
    model_names: list[str],
    path: str | Path,
    *,
    pattern: str = "**/*.md",
    include_readability: bool = True,
    output_csv: str | Path | None = None,
    output_json: str | Path | None = None,
) -> BenchmarkResult:
    """Benchmark multiple coherence models on a set of documents.

    Runs each model through the clarify pipeline and produces detailed
    comparison metrics including correlation, timing, and score distribution stats.

    Args:
        model_names: List of HuggingFace model names to compare
            (e.g. ``["all-MiniLM-L6-v2", "all-mpnet-base-v2"]``).
        path: File, directory, or JSONL batch to score.
        pattern: Glob pattern for directory scanning.
        include_readability: Include readability metrics (default True).
        output_csv: Path to save results as CSV (optional).
        output_json: Path to save results as JSON (optional).

    Returns:
        BenchmarkResult with all metrics and raw scores.
    """
    import sys
    from .clarify import (
        _discover_batch_jsonl, _discover_directory, _score_file, _strip_frontmatter,
    )
    from .semantic_coherence import MiniLMCoherenceScorer

    # -------------------------------------------------------
    # Phase 1: Score documents with each model
    # -------------------------------------------------------
    print(f"Benchmarking {len(model_names)} models on {path}...")

    all_results: dict[str, list[tuple[Path, Any]]] = {}
    timings_by_model: dict[str, list[float]] = {}

    # Discover file list once (shared across all models). For a JSONL batch,
    # inline_content holds each entry's "content", or None to read its path.
    input_path = Path(path)
    inline_content: list[str | None]
    if input_path.is_dir():
        discovered = sorted(_discover_directory(input_path, pattern))
        inline_content = [None] * len(discovered)
    elif input_path.suffix == ".jsonl":
        entries = _discover_batch_jsonl(input_path)
        discovered = []
        for i, e in enumerate(entries):
            entry_path = Path(e.get("path", f"entry_{i}"))
            # Resolve a relative path against the batch file first, as clarify() does.
            if not entry_path.is_absolute() and (input_path.parent / entry_path).is_file():
                entry_path = input_path.parent / entry_path
            discovered.append(entry_path)
        inline_content = [
            _strip_frontmatter(e["content"]) if e.get("content") else None for e in entries
        ]
    else:
        discovered = [input_path]
        inline_content = [None]

    if not discovered:
        raise ValueError(f"No files found matching pattern '{pattern}'")

    print(f"  Found {len(discovered)} documents to score")

    for model_idx, model_name in enumerate(model_names):
        print(f"\n  Model {model_idx + 1}/{len(model_names)}: {model_name}")

        # Load coherence scorer for ALL models (they all use embeddings)
        try:
            scorer = MiniLMCoherenceScorer(model_name)
        except ImportError as exc:
            print(f"    SKIP: {exc}", file=sys.stderr)
            continue

        results_list: list[tuple[Path, Any]] = []
        elapsed_times: list[float] = []

        # Score each document individually to measure per-file timing
        for file_path, content in zip(discovered, inline_content):
            t0 = time.time()
            result = _score_file(
                file_path,
                content=content,
                include_readability=include_readability,
                coherence_scorer=scorer,
            )
            elapsed_times.append(time.time() - t0)
            results_list.append((file_path, result))

        all_results[model_name] = results_list
        timings_by_model[model_name] = elapsed_times
        print(f"    Scored {len(results_list)} documents ({sum(elapsed_times):.1f}s total)")

    # -------------------------------------------------------
    # Phase 2: Extract raw coherence scores and compute metrics
    # -------------------------------------------------------
    raw_scores: dict[str, list[tuple[str, float]]] = {}
    
    for model_name, results in all_results.items():
        scores = []
        for file_path, result in results:
            score = getattr(result, "context_coherence", 50.0) or 50.0
            scores.append((str(file_path), score))
        raw_scores[model_name] = scores

    benchmark = BenchmarkResult(
        n_documents=len(list(all_results.values())[0]) if all_results else 0,
        raw_scores=raw_scores,
    )

    # Generate pairwise comparisons
    model_names_actual = list(all_results.keys())
    for i in range(len(model_names_actual) - 1):
        a_name = model_names_actual[i]
        b_name = model_names_actual[i + 1]
        metrics = _compute_comparison(
            a_name, b_name,
            raw_scores[a_name], raw_scores[b_name],
            timings_by_model.get(a_name, []),
            timings_by_model.get(b_name, []),
        )
        benchmark.comparisons.append(metrics)

    # -------------------------------------------------------
    # Phase 3: Output results
    # -------------------------------------------------------
    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)

    for comp in benchmark.comparisons:
        _print_comparison(comp)

    if output_json:
        Path(output_json).write_text(benchmark.to_json(), encoding="utf-8")
        print(f"\nJSON results saved to: {output_json}")

    return benchmark


def _compute_comparison(
    model_a_name: str,
    model_b_name: str,
    scores_a: list[tuple[str, float]],
    scores_b: list[tuple[str, float]],
    times_a: Sequence[float],
    times_b: Sequence[float],
) -> ComparisonMetrics:
    """Compute comparison metrics between two models."""
    # Align by document (use documents present in both)
    doc_to_a = dict(scores_a)
    doc_to_b = dict(scores_b)

    common_docs = set(doc_to_a.keys()) & set(doc_to_b.keys())
    
    # Extract coherence scores (filter out None/missing)
    coh_a = [doc_to_a[d] for d in sorted(common_docs)]
    coh_b = [doc_to_b[d] for d in sorted(common_docs)]

    if len(coh_a) < 2:
        return ComparisonMetrics(
            model_a_name=model_a_name,
            model_b_name=model_b_name,
            n_documents=len(common_docs),
        )

    # Rank agreement: concordant / (concordant + discordant) document pairs,
    # leaving out pairs that either model ties. With no such pairs it is 100.
    concordant = 0
    discordant = 0
    docs = sorted(common_docs)
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            diff_a = doc_to_a[docs[i]] - doc_to_a[docs[j]]
            diff_b = doc_to_b[docs[i]] - doc_to_b[docs[j]]
            if diff_a * diff_b > 0:
                concordant += 1
            elif diff_a * diff_b < 0:
                discordant += 1

    ordered_pairs = concordant + discordant
    rank_agreement = concordant / ordered_pairs * 100.0 if ordered_pairs else 100.0

    # MAE and MSE on raw scores
    errors = [(a - b) for a, b in zip(coh_a, coh_b)]
    mae = sum(abs(e) for e in errors) / len(errors)
    mse = sum(e ** 2 for e in errors) / len(errors)

    # Averages and stds
    import math as _math
    def stats(vals: list[float]) -> tuple[float, float]:
        n = len(vals)
        if n == 0:
            return 0.0, 0.0
        m = sum(vals) / n
        var = sum((v - m) ** 2 for v in vals) / max(n - 1, 1)
        return m, _math.sqrt(var)

    mean_a, std_a = stats(coh_a)
    mean_b, std_b = stats(coh_b)

    # Timing
    avg_time_a = (sum(times_a) / len(times_a) * 1000) if times_a else 0.0
    avg_time_b = (sum(times_b) / len(times_b) * 1000) if times_b else 0.0
    total_ms = (sum(times_a) + sum(times_b)) * 1000

    return ComparisonMetrics(
        model_a_name=model_a_name,
        model_b_name=model_b_name,
        n_documents=len(common_docs),
        pearson_r=_pearson(coh_a, coh_b),
        spearman_rho=_spearman(coh_a, coh_b),
        rank_agreement_pct=rank_agreement,
        mean_absolute_error=mae,
        mean_squared_error=mse,
        model_a_mean_coherence=mean_a,
        model_a_std_coherence=std_a,
        model_b_mean_coherence=mean_b,
        model_b_std_coherence=std_b,
        model_a_avg_time_ms=avg_time_a,
        model_b_avg_time_ms=avg_time_b,
        total_runtime_ms=total_ms,
        overhead_ratio=(avg_time_b / avg_time_a) if avg_time_a > 0 else 1.0,
    )


# ============================================================
# Pretty printing
# ============================================================


def _print_comparison(m: ComparisonMetrics) -> None:
    """Print a comparison result in human-readable format."""
    print(f"\n--- {m.model_a_name} vs {m.model_b_name} ---")
    print(f"  Documents compared:      {m.n_documents}")
    print(f"  Pearson r (coherence):   {m.pearson_r:.4f}")
    print(f"  Spearman ρ (coherence):  {m.spearman_rho:.4f}")
    print(f"  Rank agreement:          {m.rank_agreement_pct:.1f}%")
    print(f"  MAE (raw scores):        {m.mean_absolute_error:.2f}")
    print(f"  MSE (raw scores):        {m.mean_squared_error:.2f}")
    print("\n  Model A coherence:")
    print(f"    Mean: {m.model_a_mean_coherence:.1f}  Std: {m.model_a_std_coherence:.1f}")
    print(f"    Avg time: {m.model_a_avg_time_ms:.0f}ms / doc")
    print("\n  Model B coherence:")
    print(f"    Mean: {m.model_b_mean_coherence:.1f}  Std: {m.model_b_std_coherence:.1f}")
    print(f"    Avg time: {m.model_b_avg_time_ms:.0f}ms / doc")
    if m.overhead_ratio > 1.0:
        print(f"\n  Overhead ratio (B/A):    {m.overhead_ratio:.1f}x slower")


def generate_recommendation(metrics_list: list[ComparisonMetrics]) -> str:
    """Generate a recommendation based on benchmark results.

    Args:
        metrics_list: Comparison metrics from multiple model pairs.

    Returns:
        Text recommendation string.
    """
    if not metrics_list:
        return "No comparison data available."

    # Use the last comparison (most expensive model is always compared against baseline or previous)
    latest = metrics_list[-1]
    
    recommendations = []
    
    # Correlation quality
    if latest.pearson_r > 0.90:
        recommendations.append(f"High agreement (r={latest.pearson_r:.3f}) between models — both capture similar signal.")
    elif latest.pearson_r > 0.70:
        recommendations.append(f"Moderate-high agreement (r={latest.pearson_r:.3f}) — useful for differentiation, minor disagreements on edge cases.")
    else:
        recommendations.append(f"Low agreement (r={latest.pearson_r:.3f}) — models may be capturing different aspects.")

    # Runtime overhead
    if latest.overhead_ratio > 5.0:
        recommendations.append(
            f"{latest.model_b_name} is {latest.overhead_ratio:.1f}x slower than "
            f"{latest.model_a_name}. Consider using the faster model unless coherence quality justifies overhead."
        )
    elif latest.overhead_ratio > 2.0:
        recommendations.append(
            f"{latest.model_b_name} is {latest.overhead_ratio:.1f}x slower — acceptable tradeoff if score variance improves."
        )

    # Score variance improvement
    if latest.model_b_std_coherence > latest.model_a_std_coherence * 1.2:
        recommendations.append(
            f"{latest.model_b_name} produces more varied scores "
            f"(std={latest.model_b_std_coherence:.1f} vs {latest.model_a_std_coherence:.1f}) — better at differentiation."
        )

    return " | ".join(recommendations)

__all__ = [
    "BenchmarkResult",
    "ComparisonMetrics",
    "ModelTiming",
    "ScorePair",
    "compare_models_benchmark",
    "generate_recommendation",
]
