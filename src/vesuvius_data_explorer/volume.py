"""Deprecated compatibility module; import from vesuvius_data_explorer.core.volume."""

from .core.volume import (
    Level,
    get_array,
    list_levels,
    normalized_preview,
    open_multiscale,
    open_volume_store,
    read_slice,
    slice_stats,
    volume_summary,
)

__all__ = [
    "Level",
    "get_array",
    "list_levels",
    "normalized_preview",
    "open_multiscale",
    "open_volume_store",
    "read_slice",
    "slice_stats",
    "volume_summary",
]
