"""Per-asset prompt-profile auto-routing (documents/spreadsheets/audio)."""

from __future__ import annotations

import engine
from server.routes import analysis as analysis_route


def _run(files, profile, monkeypatch, extract=lambda p, kind: "payload"):
    """Run ``run_analysis`` with extraction + AI stubbed, capturing profiles."""
    seen: list[tuple[str, str]] = []

    def fake_asset(preview, **kwargs):
        seen.append((preview, engine.get_active_profile()))
        return {"ok": True, "data": {"new_filename": "x", "suggested_category": "uncategorized"}}

    def fake_doc(preview, **kwargs):
        seen.append((preview, engine.get_active_profile()))
        return {"ok": True, "data": {"new_filename": "x", "suggested_category": "uncategorized"}}

    # run_analysis() persists the selected profile; keep the real config.json
    # untouched so a test that flips auto_route cannot leak to disk.
    monkeypatch.setattr(engine, "save_config", lambda: None)
    monkeypatch.setattr(engine, "_llamacpp_server_running", lambda: True)
    monkeypatch.setattr(analysis_route, "_extract", extract)
    monkeypatch.setattr(engine, "analyze_asset_with_ai", fake_asset)
    monkeypatch.setattr(engine, "analyze_document_with_ai", fake_doc)
    out = analysis_route.run_analysis([str(f) for f in files], profile, {})
    return out, seen


class TestAssetKind:
    def test_visual_and_text_kinds(self):
        cases = {
            "a.mp4": "video",
            "b.jpg": "image",
            "c.pdf": "document",
            "d.rtf": "document",
            "e.md": "document",
            "f.csv": "spreadsheet",
            "g.xlsx": "spreadsheet",
            "h.mp3": "audio",
            "i.wav": "audio",
        }
        for name, expected in cases.items():
            assert engine.asset_kind(name) == expected, name

    def test_unknown_extension_is_image(self):
        assert engine.asset_kind("mystery.bin") == "image"


class TestResolveProfile:
    def test_visual_keeps_selection(self):
        assert engine.resolve_profile_for_path("clip.mp4", "cinematography") == "cinematography"

    def test_document_routes_to_document_naming(self):
        assert engine.resolve_profile_for_path("report.pdf", "cinematography") == "document_naming"

    def test_spreadsheet_routes_to_spreadsheet_naming(self):
        assert engine.resolve_profile_for_path("sheet.csv", "cinematography") == "spreadsheet_naming"

    def test_audio_routes_to_audio_naming(self):
        assert engine.resolve_profile_for_path("track.mp3", "cinematography") == "audio_naming"

    def test_routing_disabled_keeps_selection(self):
        for name in ("report.pdf", "sheet.csv", "track.mp3"):
            assert (
                engine.resolve_profile_for_path(name, "cinematography", auto_route=False)
                == "cinematography"
            )

    def test_unknown_selection_falls_back_to_active(self):
        active = engine.get_active_profile()
        assert engine.resolve_profile_for_path("clip.mp4", "does_not_exist") == active
        assert engine.resolve_profile_for_path("clip.mp4", None) == active

    def test_auto_route_config_default_is_on(self):
        assert engine.auto_route_enabled() is True


class TestProfileScope:
    def test_scope_changes_and_restores_active(self):
        original = engine.get_active_profile()
        with engine.profile_scope("document_naming"):
            assert engine.get_active_profile() == "document_naming"
        assert engine.get_active_profile() == original

    def test_scope_unknown_profile_is_a_no_op(self):
        original = engine.get_active_profile()
        with engine.profile_scope("nope_not_a_profile") as effective:
            assert effective == original
            assert engine.get_active_profile() == original
        assert engine.get_active_profile() == original

    def test_scope_does_not_persist(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(engine, "save_config", lambda: calls.append(1))
        with engine.profile_scope("audio_naming"):
            pass
        assert calls == []

    def test_categories_come_from_scoped_profile(self):
        with engine.profile_scope("document_naming"):
            assert "invoices" in engine.get_active_categories()
        with engine.profile_scope("audio_naming"):
            assert "voiceover" in engine.get_active_categories()
            assert "invoices" not in engine.get_active_categories()

    def test_prompt_includes_profile_categories(self):
        with engine.profile_scope("document_naming"):
            assert '"invoices"' in engine.get_active_prompt()


class TestRunAnalysisRouting:
    def test_mixed_batch_uses_routed_profiles(self, tmp_path, monkeypatch):
        img = tmp_path / "clip.jpg"
        img.write_bytes(b"x")
        pdf = tmp_path / "report.pdf"
        pdf.write_bytes(b"x")
        xls = tmp_path / "sheet.xlsx"
        xls.write_bytes(b"x")
        mp3 = tmp_path / "track.mp3"
        mp3.write_bytes(b"x")

        out, seen = _run([img, pdf, xls, mp3], "cinematography", monkeypatch)

        assert [p for _, p in seen] == [
            "cinematography",
            "document_naming",
            "spreadsheet_naming",
            "audio_naming",
        ]
        assert [a["profile"] for a in out] == [
            "cinematography",
            "document_naming",
            "spreadsheet_naming",
            "audio_naming",
        ]

    def test_routed_profile_does_not_leak_into_active(self, tmp_path, monkeypatch):
        # run_analysis() persists the profile the user selected; routing must not
        # leave the active profile on the document profile afterwards.
        monkeypatch.setattr(engine, "save_config", lambda: None)
        pdf = tmp_path / "report.pdf"
        pdf.write_bytes(b"x")
        _run([pdf], "cinematography", monkeypatch)
        assert engine.get_active_profile() == "cinematography"

    def test_routing_off_uses_selected_profile_for_all(self, tmp_path, monkeypatch):
        monkeypatch.setitem(engine.config["prompt_profiles"], "auto_route", False)
        pdf = tmp_path / "report.pdf"
        pdf.write_bytes(b"x")
        mp3 = tmp_path / "track.mp3"
        mp3.write_bytes(b"x")

        out, seen = _run([pdf, mp3], "cinematography", monkeypatch)

        assert [p for _, p in seen] == ["cinematography", "cinematography"]
        assert [a["profile"] for a in out] == ["cinematography", "cinematography"]
