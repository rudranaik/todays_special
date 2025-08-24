# app/core/merge.py
from __future__ import annotations

from typing import Iterable, List, Tuple

from .models import Item, Pantry


class MergeStrategy:
    """
    Placeholder for future strategy variations (e.g., 'add', 'replace', 'max').
    Today we implement 'add' semantics (sum quantities for same key).
    """
    ADD = "add"


def _index(items: Iterable[Item]) -> dict[Tuple[str, str | None], Item]:
    idx: dict[Tuple[str, str | None], Item] = {}
    for it in items:
        key = it.key()
        # Store a copy to avoid mutating original objects unexpectedly
        idx[key] = Item(**it.dict(exclude={"norm_name", "norm_unit"}))
    return idx


def merge_items(
    current: Iterable[Item],
    incoming: Iterable[Item],
    strategy: str = MergeStrategy.ADD,
) -> List[Item]:
    """
    Deterministically merge `incoming` items into `current` pantry.

    Rules (ADD):
    - Same (normalized name, normalized unit) => quantities are **summed**.
    - Unknown units are allowed but won't be cross-summed with different units.
    - If an incoming item has quantity 0, it's a no-op.
    - Negative quantities are rejected earlier by the model (ge=0). If you later want
      "consume" semantics, add a separate endpoint/command that allows negatives and
      handles stock-out logic explicitly.

    Output list is stable-sorted by (normalized_name, normalized_unit, display name) for predictability.
    """
    if strategy != MergeStrategy.ADD:
        raise ValueError(f"Unsupported merge strategy: {strategy}")

    idx = _index(current)

    for inc in incoming:
        key = inc.key()
        if inc.quantity == 0:
            # Skip explicit no-ops
            continue
        if key in idx:
            combined = idx[key]
            combined.quantity = round(combined.quantity + inc.quantity, 6)  # avoid float drift
            idx[key] = combined
        else:
            # Insert new
            idx[key] = Item(**inc.dict(exclude={"norm_name", "norm_unit"}))

    # Remove zero-quantity rows that might result from future strategies; keep all for now
    merged = list(idx.values())

    # Stable deterministic order
    merged.sort(key=lambda it: (it.normalized_name(), it.normalized_unit() or "", it.name))
    return merged


def apply_merge(
    pantry: Pantry,
    incoming_items: Iterable[Item],
    strategy: str = MergeStrategy.ADD,
) -> Pantry:
    """Helper that returns a **new** Pantry with merged items."""
    merged = merge_items(pantry.items, incoming_items, strategy=strategy)
    return Pantry(items=merged)
