"""Caption style designer presets: schema, validation, storage and conversion to render styles."""
import copy
import json
import re
import threading
import uuid
from pathlib import Path

from . import config, ctx

ALLOWED_FONTS = ("Poppins ExtraBold", "Anton", "Archivo Black")
ALLOWED_POSITIONS = ("top", "middle", "bottom")
_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
_lock = threading.RLock()


def rgb_to_ass(hex_color: str) -> str:
    """Converts #RRGGBB to ASS &HBBGGRR format (returns BBGGRR)."""
    m = _HEX_RE.match(str(hex_color).strip())
    if not m:
        return "FFFFFF"
    c = m.group(1).upper()
    r, g, b = c[0:2], c[2:4], c[4:6]
    return f"{b}{g}{r}"


def ass_to_rgb(ass_color: str) -> str:
    """Converts ASS BBGGRR format to #RRGGBB."""
    m = _HEX_RE.match(str(ass_color).strip())
    if not m:
        return "#FFFFFF"
    c = m.group(1).upper()
    b, g, r = c[0:2], c[2:4], c[4:6]
    return f"#{r}{g}{b}"


BUILTIN_PRESETS = {
    "bounce": {
        "id": "bounce",
        "name": "Bounce",
        "font": "Poppins ExtraBold",
        "size": 132,
        "primary_color": "#FFFFFF",
        "highlight_color": "#FFF000",
        "outline_color": "#000000",
        "outline_width": 7,
        "shadow": 0,
        "position": "bottom",
        "uppercase": True,
        "max_words_per_line": 3,
        "builtin": True,
    },
    "hype": {
        "id": "hype",
        "name": "Hype",
        "font": "Anton",
        "size": 152,
        "primary_color": "#FFFFFF",
        "highlight_color": "#FF3C3C",
        "outline_color": "#000000",
        "outline_width": 7,
        "shadow": 0,
        "position": "bottom",
        "uppercase": True,
        "max_words_per_line": 2,
        "builtin": True,
    },
    "clean": {
        "id": "clean",
        "name": "Clean",
        "font": "Poppins ExtraBold",
        "size": 100,
        "primary_color": "#FFFFFF",
        "highlight_color": "#6BD7FF",
        "outline_color": "#000000",
        "outline_width": 5,
        "shadow": 0,
        "position": "bottom",
        "uppercase": False,
        "max_words_per_line": 4,
        "builtin": True,
    },
}


def validate_preset(data: dict) -> dict:
    """Validates and sanitizes a caption style preset. Rejects invalid inputs with ValueError."""
    if not isinstance(data, dict):
        raise ValueError("Preset must be an object.")

    name = str(data.get("name") or "").strip()
    name = re.sub(r"[\x00-\x1f\x7f]+", " ", name).strip()[:40]
    if not name:
        raise ValueError("Preset name is required.")

    font = str(data.get("font") or "").strip()
    if font not in ALLOWED_FONTS:
        font = ALLOWED_FONTS[0]

    try:
        size = int(data.get("size", 132))
    except (ValueError, TypeError):
        size = 132
    size = max(60, min(220, size))

    primary = str(data.get("primary_color") or "#FFFFFF").strip()
    if not _HEX_RE.match(primary):
        primary = "#FFFFFF"
    elif not primary.startswith("#"):
        primary = "#" + primary

    highlight = str(data.get("highlight_color") or "#FFF000").strip()
    if not _HEX_RE.match(highlight):
        highlight = "#FFF000"
    elif not highlight.startswith("#"):
        highlight = "#" + highlight

    outline_col = str(data.get("outline_color") or "#000000").strip()
    if not _HEX_RE.match(outline_col):
        outline_col = "#000000"
    elif not outline_col.startswith("#"):
        outline_col = "#" + outline_col

    try:
        outline_w = int(data.get("outline_width", 7))
    except (ValueError, TypeError):
        outline_w = 7
    outline_w = max(0, min(20, outline_w))

    try:
        shadow = int(data.get("shadow", 0))
    except (ValueError, TypeError):
        shadow = 0
    shadow = max(0, min(10, shadow))

    pos = str(data.get("position") or "bottom").strip().lower()
    if pos not in ALLOWED_POSITIONS:
        pos = "bottom"

    uppercase = bool(data.get("uppercase", True))

    try:
        max_words = int(data.get("max_words_per_line", 3))
    except (ValueError, TypeError):
        max_words = 3
    max_words = max(1, min(6, max_words))

    return {
        "name": name,
        "font": font,
        "size": size,
        "primary_color": primary.upper(),
        "highlight_color": highlight.upper(),
        "outline_color": outline_col.upper(),
        "outline_width": outline_w,
        "shadow": shadow,
        "position": pos,
        "uppercase": uppercase,
        "max_words_per_line": max_words,
    }


def to_ass_style(preset_or_name) -> dict:
    """Converts a preset name or dict into the internal dictionary expected by studio.render.build_ass."""
    if isinstance(preset_or_name, str):
        key = preset_or_name.strip()
        if key in BUILTIN_PRESETS:
            preset = BUILTIN_PRESETS[key]
        else:
            preset = get_preset(key) or BUILTIN_PRESETS["bounce"]
    elif isinstance(preset_or_name, dict):
        preset = preset_or_name
    else:
        preset = BUILTIN_PRESETS["bounce"]

    return {
        "label": preset.get("name", "Custom"),
        "font": preset.get("font", "Poppins ExtraBold"),
        "size": preset.get("size", 132),
        "base": rgb_to_ass(preset.get("primary_color", "#FFFFFF")),
        "active": rgb_to_ass(preset.get("highlight_color", "#FFF000")),
        "strong": rgb_to_ass(preset.get("primary_color", "#FFFFFF")),
        "outline": preset.get("outline_width", 7),
        "pop": 112,
        "upper": preset.get("uppercase", True),
        "per": preset.get("max_words_per_line", 3),
        "position": preset.get("position", "bottom"),
    }


def _file(uid: str = "") -> Path | None:
    user_id = uid
    if not user_id:
        try:
            user_id = ctx.uid()
        except Exception:
            return None
    try:
        return config.user_dir(user_id) / "caption_presets.json"
    except ValueError:
        return None


def list_presets(uid: str = "") -> list:
    """Lists all available presets for the active or specified user: built-ins first, then custom."""
    items = [copy.deepcopy(p) for p in BUILTIN_PRESETS.values()]
    target = _file(uid)
    if target and target.is_file():
        try:
            custom = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(custom, list):
                items.extend(custom)
        except (OSError, ValueError):
            pass
    return items


def get_preset(pid: str, uid: str = "") -> dict | None:
    """Gets a specific preset by ID."""
    pid = str(pid).strip()
    if pid in BUILTIN_PRESETS:
        return copy.deepcopy(BUILTIN_PRESETS[pid])
    for p in list_presets(uid):
        if p.get("id") == pid:
            return p
    return None


def save_preset(data: dict, uid: str = "") -> dict:
    """Creates or updates a custom preset for the current user."""
    clean = validate_preset(data)
    pid = str(data.get("id") or "").strip()
    is_new = not pid or pid in BUILTIN_PRESETS

    with _lock:
        target = _file(uid)
        if not target:
            raise ValueError("No valid user session for custom presets.")
        custom = []
        if target.is_file():
            try:
                custom = json.loads(target.read_text(encoding="utf-8"))
                if not isinstance(custom, list):
                    custom = []
            except (OSError, ValueError):
                custom = []

        if is_new:
            clean["id"] = "p_" + uuid.uuid4().hex[:10]
            clean["builtin"] = False
            custom.append(clean)
        else:
            found = False
            for i, p in enumerate(custom):
                if p.get("id") == pid:
                    clean["id"] = pid
                    clean["builtin"] = False
                    custom[i] = clean
                    found = True
                    break
            if not found:
                clean["id"] = pid
                clean["builtin"] = False
                custom.append(clean)

        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(custom, indent=2), encoding="utf-8")
        tmp.replace(target)

    try:
        ctx.bump()
    except Exception:
        pass
    return clean


def delete_preset(pid: str, uid: str = "") -> bool:
    """Deletes a custom preset. Built-in presets cannot be deleted."""
    pid = str(pid).strip()
    if pid in BUILTIN_PRESETS:
        raise ValueError("Built-in presets cannot be deleted.")

    with _lock:
        target = _file(uid)
        if not target or not target.is_file():
            return False
        try:
            custom = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False

        orig_len = len(custom)
        custom = [p for p in custom if p.get("id") != pid]
        if len(custom) == orig_len:
            return False

        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(custom, indent=2), encoding="utf-8")
        tmp.replace(target)

    try:
        ctx.bump()
    except Exception:
        pass
    return True
