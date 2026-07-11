
from engine import sanitize_name, validate_category


class TestValidateCategory:
    def test_validate_category_valid(self):
        result, was_fallback = validate_category("aerial_drone")
        assert result == "aerial_drone"
        assert was_fallback is False

    def test_validate_category_invalid_returns_uncategorized(self):
        result, was_fallback = validate_category("nonexistent_category_xyz")
        assert result == "uncategorized"
        assert was_fallback is True

    def test_validate_category_empty_returns_uncategorized(self):
        result, was_fallback = validate_category("")
        assert result == "uncategorized"
        assert was_fallback is True

    def test_validate_category_none_returns_uncategorized(self):
        result, was_fallback = validate_category(None)
        assert result == "uncategorized"
        assert was_fallback is True

    def test_validate_category_case_insensitive(self):
        result, was_fallback = validate_category("Aerial_Drone")
        assert result == "aerial_drone"
        assert was_fallback is False

    def test_validate_category_whitespace_stripped(self):
        result, was_fallback = validate_category("  aerial_drone  ")
        assert result == "aerial_drone"
        assert was_fallback is False


class TestSanitizeName:
    def test_sanitize_name_removes_special_chars(self):
        result = sanitize_name("hello@world#$test")
        assert "@" not in result
        assert "#" not in result
        assert "$" not in result

    def test_sanitize_name_lowercases(self):
        result = sanitize_name("HELLO_WORLD_TEST")
        assert result == "hello_world_test"

    def test_sanitize_name_adds_default_suffix_if_too_short(self):
        result = sanitize_name("short")
        assert result.endswith("_media_asset")

    def test_sanitize_name_removes_grid_and_sequence(self):
        result = sanitize_name("sunset_grid_sequence_view")
        assert "grid" not in result
        assert "sequence" not in result

    def test_sanitize_name_strips_leading_trailing_underscores(self):
        result = sanitize_name("_hello_world_test_")
        assert not result.startswith("_")
        assert not result.endswith("_")
