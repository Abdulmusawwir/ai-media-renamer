import json

from engine import _parse_ai_response


class TestParseAiResponse:
    def test_parse_valid_json(self):
        data = {
            "new_filename": "aerial_view_of_coastline",
            "tags": ["coast", "ocean"],
            "overall_visual_summary": "Aerial drone shot of coastline",
        }
        raw = json.dumps(data)
        result, error, detail = _parse_ai_response(raw)
        assert error is None
        assert detail is None
        assert result == data

    def test_parse_codeblock_json(self):
        raw = '```json\n{"new_filename": "sunset_over_mountains", "tags": ["sunset", "mountains"]}\n```'
        result, error, detail = _parse_ai_response(raw)
        assert error is None
        assert result["new_filename"] == "sunset_over_mountains"

    def test_parse_codeblock_no_lang(self):
        raw = '```\n{"new_filename": "test_footage"}\n```'
        result, error, detail = _parse_ai_response(raw)
        assert error is None
        assert result["new_filename"] == "test_footage"

    def test_parse_empty_response(self):
        result, error, detail = _parse_ai_response("")
        assert result is None
        assert error == "empty_response"
        assert detail is not None

    def test_parse_whitespace_only(self):
        result, error, detail = _parse_ai_response("   \n\n   ")
        assert result is None
        assert error == "empty_response"

    def test_parse_malformed_json(self):
        result, error, detail = _parse_ai_response('{"new_filename": "broken')
        assert result is None
        assert error == "json_parse_error"
        assert detail is not None

    def test_parse_nested_json_works(self):
        raw = json.dumps({
            "new_filename": "city_timelapse", "tags": ["city", "night"],
            "overall_visual_summary": "Timelapse of city skyline at night",
            "cinematography": {"shot_type": "wide", "lighting": "night"},
        })
        result, error, detail = _parse_ai_response(raw)
        assert error is None
        assert result["cinematography"]["shot_type"] == "wide"
