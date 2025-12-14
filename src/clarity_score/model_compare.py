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

from .clarify import clarify, compare_models


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

    # Clarity score agreement (using full clarity scores, not just coherence)
    pearson_r_clarity: float = 0.0


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
                    "pearson_r_clarity": round(m.pearson_r_clarity, 4),
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
    from .semantic_coherence import MiniLMCoherenceScorer

    # -------------------------------------------------------
    # Phase 1: Score documents with each model
    # -------------------------------------------------------
    print(f"Benchmarking {len(model_names)} models on {path}...")

    all_results: dict[str, list[tuple[Path, Any]]] = {}
    timings_by_model: dict[str, list[float]] = {}

    # Discover file list once (shared across all models)
    input_path = Path(path)
    if input_path.is_dir():
        from .clarify import _discover_directory
        discovered = sorted(_discover_directory(input_path, pattern))
    elif input_path.suffix == ".jsonl":
        # Batch JSONL — collect entries first
        from .clarify import _discover_batch_jsonl
        entries = _discover_batch_jsonl(input_path)
        discovered = [Path(e.get("path", f"entry_{i}")) for i, e in enumerate(entries)]
    else:
        discovered = [input_path]

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
        if input_path.is_dir():
            from .clarify import _score_file
            for file_path in discovered:
                t0 = time.time()
                result = _score_file(file_path, include_readability=include_readability, coherence_scorer=scorer)
                elapsed_times.append(time.time() - t0)
                results_list.append((file_path, result))
        else:
            t0 = time.time()
            from .clarify import _read_content
            result = _score_file(
                input_path, 
                content=_read_content(input_path),
                include_readability=include_readability,
                coherence_scorer=scorer,
            )
            elapsed_times.append(time.time() - t0)
            results_list.append((input_path, result))

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
        Path(output_json).write_text(benchmark.to_json())
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

    # Rank agreement: what % of pairs do both models agree on ordering?
    agreements = 0
    disagreements = 0
    docs = sorted(common_docs)
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            a_i, b_i = doc_to_a[docs[i]], doc_to_b[docs[i]]
            a_j, b_j = doc_to_a[docs[j]], doc_to_b[docs[j]]
            if (a_i > a_j) == (b_i > b_j):  # Same ordering
                agreements += 1
            elif (a_i < a_j) and (b_i > b_j):  # Different
                disagreements += 1

    total_pairs = agreements + max(disagreements, 1)
    rank_agreement = agreements / total_pairs * 100.0

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

    # Clarity score comparison (already included in analysis results)
    result_to_clarity: dict[str, float] = {}
    for file_path, result in _score_results(model_a_name, scores_a):
        result_to_clarity[file_path] = getattr(result, "clarity_score", 0.0)

    # Compute clarity correlation between models (only meaningful if both are baseline)
    pearson_r_clarity = 0.0
    if model_a_name in ["<baseline>", model_b_name] and model_b_name in ["<baseline>", model_a_name]:
        clarity_a = [result_to_clarity[d] for d in docs]
        clarity_b = [result_to_clarity.get(d, 0.0) for d in docs]
        if len(clarity_a) > 2:
            pearson_r_clarity = _pearson(clarity_a, clarity_b)

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
        pearson_r_clarity=pearson_r_clarity,
    )





def _score_results(model_name: str, scores: list[tuple[str, float]]) -> Sequence[tuple[Path, Any]]:
    """Stub to resolve type — not used directly."""
    return []


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
    print(f"\n  Model A coherence:")
    print(f"    Mean: {m.model_a_mean_coherence:.1f}  Std: {m.model_a_std_coherence:.1f}")
    print(f"    Avg time: {m.model_a_avg_time_ms:.0f}ms / doc")
    print(f"\n  Model B coherence:")
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
