"""Shapley Value attribution (attribution.py).

Fair contribution of each behavioral pattern to total PnL using Monte Carlo
Shapley sampling. Replaces the naive "remove pattern -> recompute PnL" approach
which suffers from Attribution Overlap (when a position carries multiple labels,
removing any one drops the entire position's PnL, causing double-counting).

NOTE: This module deals with *statistical pattern contribution* (Shapley values).
For *factor contribution* (MAE/MFE breakdown, stop-loss counterfactuals), see
whatif.py which contains the ProfitAttribution class and rule-simulation engine.

Shapley Value guarantees:
     Sum of Shapley_i = total_pnl  (efficiency)
Each pattern gets a fair share of jointly-attributed PnL.

Uses Monte Carlo sampling for efficiency when N is large.
"""

import math
import random


def shapley_attribution(
    positions: list,
    patterns_map: dict[int, list[str]],
    n_samples: int = 5000,
) -> dict[str, float]:
    """Compute Shapley Value for each pattern via Monte Carlo sampling.

    Args:
        positions: List of position-like objects with .pnl.
        patterns_map: {position_index: [pattern_names]}.
        n_samples: Number of Monte Carlo samples (more = more accurate).

    Returns:
        {pattern_name: shapley_value} -- sum of all values approx total_pnl.
    """
    valid_indices = {
        i for i, p in enumerate(positions)
        if getattr(p, "cost_known", True)
    }

    # Collect unique patterns
    all_patterns: list[str] = []
    for i in valid_indices:
        for pat in patterns_map.get(i, []):
            if pat not in all_patterns:
                all_patterns.append(pat)

    n = len(all_patterns)
    if n == 0:
        return {}
    if n == 1:
        total = sum(positions[i].pnl for i in valid_indices if all_patterns[0] in patterns_map.get(i, []))
        return {all_patterns[0]: round(total, 2)}

    # Precompute: {pattern_name: set of position indices that have this pattern}
    pattern_positions: dict[str, set[int]] = {pat: set() for pat in all_patterns}
    for i in valid_indices:
        for pat in patterns_map.get(i, []):
            pattern_positions[pat].add(i)

    # Build reverse map: {position_index: mask bit}
    pos_to_bit = {i: 1 << j for j, i in enumerate(sorted(valid_indices))}
    pattern_masks: dict[str, int] = {}
    for pat in all_patterns:
        mask = 0
        for i in pattern_positions[pat]:
            mask |= pos_to_bit.get(i, 0)
        pattern_masks[pat] = mask

    # Precompute PnL per position
    pnl_per_pos = {i: positions[i].pnl for i in valid_indices}

    def coalition_value(mask: int) -> float:
        """Total PnL of positions covered by this coalition of patterns."""
        total = 0.0
        for i in valid_indices:
            if mask & pos_to_bit.get(i, 0):
                total += pnl_per_pos[i]
        return total

    # Monte Carlo Shapley
    shapley_accum: dict[str, float] = {pat: 0.0 for pat in all_patterns}
    pattern_list = list(all_patterns)

    for _ in range(n_samples):
        random.shuffle(pattern_list)
        coalition_mask = 0
        prev_value = 0.0

        for pat in pattern_list:
            new_mask = coalition_mask | pattern_masks[pat]
            new_value = coalition_value(new_mask)
            marginal = new_value - prev_value
            shapley_accum[pat] += marginal
            coalition_mask = new_mask
            prev_value = new_value

    result = {pat: round(val / n_samples, 2) for pat, val in shapley_accum.items()}

    # Normalize to ensure sum = total_pnl (corrects sampling noise)
    total_shapley = sum(result.values())
    total_pnl = sum(pnl_per_pos.values())
    if total_shapley != 0 and abs(total_shapley - total_pnl) > 0.01:
        scale = total_pnl / total_shapley
        result = {k: round(v * scale, 2) for k, v in result.items()}

    return result
