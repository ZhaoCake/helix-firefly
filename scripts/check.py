#!/usr/bin/env python3
"""Validate the Firefly Helix themes.

Checks:
  1. every file under themes/ is valid TOML
  2. every palette reference resolves to a defined color (or a literal #RRGGBB)
  3. firefly-dark and firefly-light expose the same scope keys
  4. visible text scopes meet a minimum contrast against their background
  5. reports unused palette entries (informational)

Exit code is non-zero if a hard check fails.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEMES_DIR = ROOT / "themes"
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Scopes that are intentionally low contrast or purely decorative.
SKIP_CONTRAST = {
    "ui.virtual.whitespace",
    "ui.virtual.indent-guide",
    "ui.virtual.ruler",
    "ui.window",
    "ui.gutter",
    "ui.cursor.match",
    "ui.selection",
    "ui.selection.primary",
}

HARD_MIN = 3.0   # fail below this
SOFT_MIN = 4.5   # warn below this


def luminance(hex_color: str) -> float:
    c = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a: str, b: str) -> float:
    l1, l2 = sorted((luminance(a), luminance(b)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def resolve(value, palette, path, errors):
    if not isinstance(value, str):
        errors.append(f"{path}: expected a color string, got {type(value).__name__}")
        return None
    if HEX.match(value):
        return value.upper()
    if value in palette:
        return palette[value].upper()
    errors.append(f"{path}: unresolved color {value!r}")
    return None


def walk_styles(node, path, out):
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        here = f"{path}.{key}" if path else key
        if key == "palette":
            continue
        if isinstance(value, dict):
            if any(k in value for k in ("fg", "bg", "underline", "modifiers")):
                out[here] = value
            else:
                walk_styles(value, here, out)
        elif isinstance(value, str):
            out[here] = {"fg": value}


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    scope_maps: dict[str, set[str]] = {}

    files = sorted(THEMES_DIR.glob("*.toml"))
    if not files:
        print("no themes found", file=sys.stderr)
        return 1

    for path in files:
        try:
            data = tomllib.loads(path.read_text())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.name}: TOML parse error: {exc}")
            continue

        palette = data.get("palette", {})
        if not isinstance(palette, dict):
            errors.append(f"{path.name}: [palette] must be a table")
            palette = {}
        for name, value in palette.items():
            if not isinstance(value, str) or not HEX.match(value):
                errors.append(f"{path.name}: palette.{name} is not a #RRGGBB color: {value!r}")

        styles: dict[str, dict] = {}
        walk_styles({k: v for k, v in data.items() if k != "palette"}, "", styles)
        scope_maps[path.name] = set(styles)

        used = set()
        for scope, style in styles.items():
            for slot in ("fg", "bg"):
                if slot in style:
                    if isinstance(style[slot], str) and style[slot] in palette:
                        used.add(style[slot])
                    resolve(style[slot], palette, f"{path.name}:{scope}.{slot}", errors)
            underline = style.get("underline")
            if isinstance(underline, dict) and "color" in underline:
                if isinstance(underline["color"], str) and underline["color"] in palette:
                    used.add(underline["color"])
                resolve(underline["color"], palette, f"{path.name}:{scope}.underline", errors)

        base = styles.get("ui.background", {})
        base_bg = base.get("bg") if isinstance(base.get("bg"), str) else None
        if base_bg:
            base_bg = resolve(base_bg, palette, f"{path.name}:ui.background.bg", errors)
        else:
            errors.append(f"{path.name}: ui.background has no bg")
            base_bg = "#000000"

        for scope, style in styles.items():
            if scope in SKIP_CONTRAST or "fg" not in style:
                continue
            if "bg" in style:
                bg = resolve(style["bg"], palette, f"{path.name}:{scope}.bg", errors)
            else:
                bg = base_bg
            fg = resolve(style["fg"], palette, f"{path.name}:{scope}.fg", errors)
            if not fg or not bg:
                continue
            ratio = contrast(fg, bg)
            if ratio < HARD_MIN:
                errors.append(f"{path.name}:{scope}: contrast {ratio:.2f} < {HARD_MIN} ({fg} on {bg})")
            elif ratio < SOFT_MIN:
                warnings.append(f"{path.name}:{scope}: contrast {ratio:.2f} < {SOFT_MIN} ({fg} on {bg})")

        unused = sorted(set(palette) - used)
        if unused:
            warnings.append(f"{path.name}: unused palette entries: {', '.join(unused)}")
        print(f"{path.name}: {len(styles)} scopes, {len(palette)} palette colors")

    if len(scope_maps) > 1:
        names = sorted(scope_maps)
        first = scope_maps[names[0]]
        for name in names[1:]:
            missing = first - scope_maps[name]
            extra = scope_maps[name] - first
            if missing:
                errors.append(f"{name}: missing scopes present in {names[0]}: {', '.join(sorted(missing))}")
            if extra:
                errors.append(f"{name}: extra scopes not in {names[0]}: {', '.join(sorted(extra))}")

    for warning in warnings:
        print(f"warn: {warning}")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
