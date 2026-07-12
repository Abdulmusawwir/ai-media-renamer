import json

from engine import ALLOWED_CATEGORIES, export_staging_csv, export_staging_json, import_staging_csv

SAMPLE_ASSETS = [
    {
        "original_name": "video_001.mp4",
        "staged_name": "golden_hour_aerial_coastline",
        "category": "aerial_drone",
        "tags": ["golden_hour", "coastline", "aerial"],
        "summary": "Aerial drone footage of a coastline at golden hour.",
    },
    {
        "original_name": "photo_002.jpg",
        "staged_name": "mosque_courtyard_fountain",
        "category": "architectural",
        "tags": ["mosque", "courtyard", "fountain"],
        "summary": "Interior courtyard of a mosque with a central fountain.",
    },
]


class TestExportStagingCsv:
    def test_returns_string(self):
        result = export_staging_csv(SAMPLE_ASSETS)
        assert isinstance(result, str)

    def test_contains_column_headers(self):
        result = export_staging_csv(SAMPLE_ASSETS)
        assert "original_name" in result
        assert "proposed_filename" in result
        assert "category" in result
        assert "tags" in result
        assert "summary" in result

    def test_contains_asset_data(self):
        result = export_staging_csv(SAMPLE_ASSETS)
        assert "video_001.mp4" in result
        assert "golden_hour_aerial_coastline" in result
        assert "aerial_drone" in result
        assert "golden_hour, coastline, aerial" in result

    def test_empty_list_returns_headers_only(self):
        result = export_staging_csv([])
        lines = result.strip().split("\n")
        assert len(lines) == 1
        assert "original_name" in lines[0]


class TestExportStagingJson:
    def test_returns_string(self):
        result = export_staging_json(SAMPLE_ASSETS)
        assert isinstance(result, str)

    def test_valid_json(self):
        result = export_staging_json(SAMPLE_ASSETS)
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 2

    def test_contains_expected_keys(self):
        result = export_staging_json(SAMPLE_ASSETS)
        parsed = json.loads(result)
        for item in parsed:
            assert "original_name" in item
            assert "proposed_filename" in item
            assert "category" in item
            assert "tags" in item
            assert "summary" in item

    def test_empty_list_returns_empty_array(self):
        result = export_staging_json([])
        assert result == "[]"


class TestImportStagingCsv:
    def test_parses_valid_csv(self):
        csv_data = "original_name,proposed_filename,category,tags,summary\npic.png,desert_sunset,landscapes_broll,\"sunset, desert\",warm colors\n"
        assets, warnings = import_staging_csv(csv_data, ALLOWED_CATEGORIES)
        assert len(assets) == 1
        assert assets[0]["original_name"] == "pic.png"
        assert assets[0]["staged_name"] == "desert_sunset"
        assert assets[0]["category"] == "landscapes_broll"
        assert assets[0]["tags"] == ["sunset", "desert"]
        assert len(warnings) == 0

    def test_invalid_category_falls_back(self):
        csv_data = "original_name,proposed_filename,category,tags,summary\npic.png,foobar,bogus_category,test,desc\n"
        assets, warnings = import_staging_csv(csv_data, ALLOWED_CATEGORIES)
        assert assets[0]["category"] == "uncategorized"
        assert len(warnings) == 1
        assert "unknown category" in warnings[0]

    def test_empty_csv_returns_empty(self):
        csv_data = "original_name,proposed_filename,category,tags,summary\n"
        assets, warnings = import_staging_csv(csv_data, ALLOWED_CATEGORIES)
        assert len(assets) == 0
        assert len(warnings) == 0

    def test_multiple_tags_parsed(self):
        csv_data = "original_name,proposed_filename,category,tags,summary\nf.mov,clip,landscapes_broll,\"tag1, tag2, tag3\",desc\n"
        assets, _ = import_staging_csv(csv_data, ALLOWED_CATEGORIES)
        assert assets[0]["tags"] == ["tag1", "tag2", "tag3"]

    def test_empty_category_becomes_uncategorized(self):
        csv_data = "original_name,proposed_filename,category,tags,summary\nf.mov,clip,,tag1,desc\n"
        assets, warnings = import_staging_csv(csv_data, ALLOWED_CATEGORIES)
        assert assets[0]["category"] == "uncategorized"

    def test_case_insensitive_category_normalization(self):
        csv_data = "original_name,proposed_filename,category,tags,summary\nf.mov,clip,Aerial_Drone,test,desc\n"
        assets, _ = import_staging_csv(csv_data, ALLOWED_CATEGORIES)
        assert assets[0]["category"] == "aerial_drone"
