"""Theme system — color palettes and visual styles."""
from __future__ import annotations

from typing import Any, Optional


class Theme:
    """A visual theme with color palette and style settings."""
    def __init__(self, name: str, **kwargs: Any) -> None:
        self.name = name
        self.background: str = kwargs.get("background", "white")
        self.foreground: str = kwargs.get("foreground", "black")
        self.grid: str = kwargs.get("grid", "#cccccc")
        self.primary: str = kwargs.get("primary", "#1f77b4")
        self.secondary: str = kwargs.get("secondary", "#ff7f0e")
        self.tertiary: str = kwargs.get("tertiary", "#2ca02c")
        self.positive: str = kwargs.get("positive", "green")
        self.negative: str = kwargs.get("negative", "red")
        self.cmap_diverging: str = kwargs.get("cmap_diverging", "RdYlGn")
        self.cmap_sequential: str = kwargs.get("cmap_sequential", "viridis")
        self.font_size: int = kwargs.get("font_size", 12)
        self.figsize: tuple[float, float] = kwargs.get("figsize", (12.0, 6.0))

    def to_dict(self) -> dict:
        return {
            "name": self.name, "background": self.background,
            "foreground": self.foreground, "grid": self.grid,
            "primary": self.primary, "secondary": self.secondary,
            "positive": self.positive, "negative": self.negative,
            "cmap_diverging": self.cmap_diverging,
            "cmap_sequential": self.cmap_sequential,
            "font_size": self.font_size, "figsize": list(self.figsize),
        }


_THEMES: dict[str, Theme] = {
    "default": Theme("default"),
    "dark": Theme("dark", background="#1e1e1e", foreground="#e0e0e0",
                  grid="#444444", primary="#4e9ff5", secondary="#ff9f40"),
    "publication": Theme("publication", background="white", foreground="black",
                         grid="#999999", font_size=10, figsize=(8.0, 5.0)),
}


def get_theme(name: str = "default") -> Theme:
    return _THEMES.get(name, _THEMES["default"])


def register_theme(theme: Theme) -> None:
    _THEMES[theme.name] = theme


def list_themes() -> list[str]:
    return list(_THEMES.keys())
