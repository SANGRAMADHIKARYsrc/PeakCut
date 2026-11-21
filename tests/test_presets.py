"""Check caption style presets: schema, validation, storage, user isolation, and render integration."""
import os
import sys
import tempfile
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, ".")


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


def main(data):
    os.environ.update(PEAKCUT_DATA=data, DATABASE_URL="", PEAKCUT_ACCOUNTS="1")
    from studio import auth, ctx, db, presets, render, server

    db.init()
    try:
        user_a = "user_a_id"
        user_b = "user_b_id"

        # 1. Built-in presets
        all_presets = presets.list_presets()
        check("built-in presets list includes bounce, hype, and clean",
              len(all_presets) >= 3 and {"bounce", "hype", "clean"}.issubset({p["id"] for p in all_presets}))
        check("built-ins are flagged as builtin",
              all(p["builtin"] for p in all_presets if p["id"] in ("bounce", "hype", "clean")))

        # 2. Cannot delete built-ins
        with ctx.as_user(user_a):
            try:
                presets.delete_preset("bounce")
                failed = False
            except ValueError:
                failed = True
            check("cannot delete built-in presets", failed)

        # 3. Validation
        valid = presets.validate_preset({
            "name": "Neon Cyan",
            "font": "Anton",
            "size": 140,
            "primary_color": "#FFFFFF",
            "highlight_color": "#00FFFF",
            "outline_color": "#000000",
            "outline_width": 8,
            "shadow": 2,
            "position": "middle",
            "uppercase": True,
            "max_words_per_line": 3,
        })
        check("valid preset passes validation with proper casing",
              valid["name"] == "Neon Cyan" and valid["font"] == "Anton" and valid["size"] == 140
              and valid["highlight_color"] == "#00FFFF" and valid["position"] == "middle")

        clamped = presets.validate_preset({
            "name": "Clamped Test",
            "font": "NonExistentFont",
            "size": 9999,
            "outline_width": 500,
            "position": "invalid_pos",
            "max_words_per_line": 20,
        })
        check("invalid values are safely clamped and defaulted",
              clamped["font"] == "Poppins ExtraBold" and clamped["size"] == 220
              and clamped["outline_width"] == 20 and clamped["position"] == "bottom"
              and clamped["max_words_per_line"] == 6)

        try:
            presets.validate_preset({"name": ""})
            name_failed = False
        except ValueError:
            name_failed = True
        check("preset without a name is rejected", name_failed)

        # 4. User isolation and CRUD
        with ctx.as_user(user_a):
            created_a = server.save_caption_preset({
                "name": "User A Style",
                "font": "Archivo Black",
                "size": 120,
                "highlight_color": "#FF8800",
                "position": "top",
            })
            check("user A can create a custom preset", created_a["id"].startswith("p_") and created_a["name"] == "User A Style")
            pids_a = {p["id"] for p in server.list_caption_presets()}
            check("created preset appears in user A's preset list", created_a["id"] in pids_a)

        with ctx.as_user(user_b):
            pids_b = {p["id"] for p in server.list_caption_presets()}
            check("user B cannot see user A's custom preset", created_a["id"] not in pids_b)

            try:
                server.delete_caption_preset(created_a["id"])
                del_forbidden = False
            except HTTPException:
                del_forbidden = True
            check("user B cannot delete user A's preset", del_forbidden)

        # 5. Conversion to ASS style and render integration
        ass_style = presets.to_ass_style(created_a)
        check("converts to ASS style dictionary properly",
              ass_style["font"] == "Archivo Black" and ass_style["size"] == 120
              and ass_style["position"] == "top" and ass_style["active"] == presets.rgb_to_ass("#FF8800"))

        words = [{"w": "Hello", "s": 0.0, "e": 0.5}, {"w": "World", "s": 0.5, "e": 1.0}]
        ass_text = render.build_ass(words, 0.0, 1.0, "MY HOOK", created_a, [], 200, 1400)
        check("render.build_ass builds valid ASS with custom preset",
              "Style: Cap,Archivo Black,120" in ass_text and "Dialogue: " in ass_text)

        # 6. Delete custom preset
        with ctx.as_user(user_a):
            server.delete_caption_preset(created_a["id"])
            pids_after = {p["id"] for p in server.list_caption_presets()}
            check("user A can delete their custom preset", created_a["id"] not in pids_after)

    finally:
        db.engine.dispose()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="pc-presets-") as data:
        main(data)
