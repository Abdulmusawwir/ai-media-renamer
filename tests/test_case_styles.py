"""Comprehensive tests for case style transformations and sanitize_name"""

import sys

sys.path.insert(0, '.')
from engine import apply_case_style, sanitize_name, truncate_filename


def test_sanitize_name():
    cases = [
        ("golden_hour_aerial_coastline", "golden_hour_aerial_coastline"),
        ("Golden Hour Aerial Coastline", "golden_hour_aerial_coastline"),
        ("Aerial_Drone_Shot", "aerial_drone_shot"),
        ("grid_motion_graphics", "motion_graphics_media_asset"),
        ("sequence_desert_view", "desert_view_media_asset"),
        ("scene-4k-motion-graphic!", "scene-4k-motion-graphic_media_asset"),
        ("  with_spaces  ", "with_spaces_media_asset"),
        ("__leading_trailing__", "leading_trailing_media_asset"),
        ("a_b", "a_b_media_asset"),
    ]
    for raw, expected in cases:
        result = sanitize_name(raw)
        assert result == expected, f"santize_name({raw!r}) = {result!r}, expected {expected!r}"
    print(f"  sanitize_name: {len(cases)} cases PASS")


def test_snake_case():
    cases = [
        ("golden_hour_aerial_coastline", "golden_hour_aerial_coastline"),
        ("golden-hour-aerial-coastline", "golden_hour_aerial_coastline"),
        ("golden hour aerial coastline", "golden_hour_aerial_coastline"),
        ("Mixed_Case_Example", "mixed_case_example"),
        ("a_b_c", "a_b_c"),
    ]
    for inp, expected in cases:
        result = apply_case_style(inp, "snake_case")
        assert result == expected, f"snake_case({inp!r}) = {result!r}, expected {expected!r}"
    print(f"  snake_case: {len(cases)} cases PASS")


def test_camel_case():
    cases = [
        ("golden_hour_aerial_coastline", "goldenHourAerialCoastline"),
        ("golden-hour-aerial-coastline", "goldenHourAerialCoastline"),
        ("golden hour aerial coastline", "goldenHourAerialCoastline"),
        ("aerial_drone_shot_media_asset", "aerialDroneShotMediaAsset"),
        ("scene_4k_motion_graphic", "scene4kMotionGraphic"),
    ]
    for inp, expected in cases:
        result = apply_case_style(inp, "camelCase")
        assert result == expected, f"camelCase({inp!r}) = {result!r}, expected {expected!r}"
    print(f"  camelCase: {len(cases)} cases PASS")


def test_kebab_case():
    cases = [
        ("golden_hour_aerial_coastline", "golden-hour-aerial-coastline"),
        ("golden-hour-aerial-coastline", "golden-hour-aerial-coastline"),
        ("golden hour aerial coastline", "golden-hour-aerial-coastline"),
        ("aerial_drone_shot", "aerial-drone-shot"),
        ("scene_4k_motion", "scene-4k-motion"),
    ]
    for inp, expected in cases:
        result = apply_case_style(inp, "kebab-case")
        assert result == expected, f"kebab-case({inp!r}) = {result!r}, expected {expected!r}"
    print(f"  kebab-case: {len(cases)} cases PASS")


def test_pascal_case():
    cases = [
        ("golden_hour_aerial_coastline", "GoldenHourAerialCoastline"),
        ("golden-hour-aerial-coastline", "GoldenHourAerialCoastline"),
        ("golden hour aerial coastline", "GoldenHourAerialCoastline"),
        ("aerial_drone_shot", "AerialDroneShot"),
        ("scene_4k_motion", "Scene4kMotion"),
    ]
    for inp, expected in cases:
        result = apply_case_style(inp, "pascal_case")
        assert result == expected, f"pascal_case({inp!r}) = {result!r}, expected {expected!r}"
    print(f"  pascal_case: {len(cases)} cases PASS")


def test_lowercase():
    cases = [
        ("golden_hour_aerial_coastline", "goldenhouraerialcoastline"),
        ("golden-hour-aerial-coastline", "goldenhouraerialcoastline"),
        ("golden hour aerial coastline", "goldenhouraerialcoastline"),
        ("Mixed_Case_Example", "mixedcaseexample"),
        ("a_b_c", "abc"),
    ]
    for inp, expected in cases:
        result = apply_case_style(inp, "lowercase")
        assert result == expected, f"lowercase({inp!r}) = {result!r}, expected {expected!r}"
    print(f"  lowercase: {len(cases)} cases PASS")


def test_truncate_filename():
    cases = [
        ("golden_hour_aerial_coastline", 0, "golden_hour_aerial_coastline"),
        ("golden_hour_aerial_coastline", 100, "golden_hour_aerial_coastline"),
        ("golden_hour_aerial_coastline", 10, "golden_hou"),
        ("golden_hour_aerial_coastline", 22, "golden_hour_aerial_coa"),
        ("golden-hour-aerial", 6, "golden"),
        ("golden_hour_", 10, "golden_hou"),
        ("golden-hour-aerial-", 8, "golden-h"),
    ]
    for inp, max_chars, expected in cases:
        result = truncate_filename(inp, max_chars)
        assert result == expected, f"truncate_filename({inp!r}, {max_chars}) = {result!r}, expected {expected!r}"
    print(f"  truncate_filename: {len(cases)} cases PASS")


def test_end_to_end():
    """Simulate the full app pipeline: AI output -> sanitize -> case style -> truncate"""
    ai_names = [
        "golden_hour_aerial_coastline",
        "night_city_skyline_timelapse",
        "macro_water_droplets_green_leaf",
        "desert_dunes_aerial_drone",
        "islamic_mosque_dome_interior",
    ]
    for raw_name in ai_names:
        safe = sanitize_name(raw_name)
        styled = apply_case_style(safe, "camelCase")
        truncated = truncate_filename(styled, 0)
        assert "_" not in truncated, f"camelCase output still has underscores: {truncated}"
        assert truncated[0].islower(), f"camelCase output starts uppercase: {truncated}"
    print(f"  end_to_end: {len(ai_names)} cases PASS")


if __name__ == "__main__":
    tests = [
        test_sanitize_name,
        test_snake_case,
        test_camel_case,
        test_kebab_case,
        test_pascal_case,
        test_lowercase,
        test_truncate_filename,
        test_end_to_end,
    ]
    failures = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"  FAIL: {t.__name__}: {e}")
            failures += 1
    total = len(tests)
    passed = total - failures
    print(f"\n{'='*40}")
    print(f"Results: {passed}/{total} passed, {failures} failed")
    sys.exit(failures)
