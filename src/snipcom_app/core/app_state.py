from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ProfileUiState:
    remove_window_bar: bool = False
    background_path: str = ""
    table_zoom_percent: int = 100
    grid_zoom_percent: int = 100
    view_mode: str = "table"
    sort_column: int = 0
    sort_order_desc: bool = False
    selected_grid_tags: set[str] = field(default_factory=set)
    selected_family_filter: str = ""
    pinned_families: set[str] = field(default_factory=set)
    recent_search_queries: list[str] = field(default_factory=list)
    window_width: int = 812
    window_height: int = 560
    column_widths: list[int] = field(default_factory=list)
    column_order: list[int] = field(default_factory=list)
