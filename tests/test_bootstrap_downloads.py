import zipfile

import bootstrap


class TestExiftoolDownloadUrls:
    def test_first_url_uses_dynamic_version(self, monkeypatch):
        class _FakeResp:
            text = "13.59"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(bootstrap.requests, "get",
                            lambda url, timeout: _FakeResp())
        urls = bootstrap._exiftool_download_urls()
        assert urls[0] == (
            "https://sourceforge.net/projects/exiftool/files/"
            "exiftool-13.59_64.zip/download"
        )

    def test_ver_txt_failure_falls_back_to_pinned_versions(self, monkeypatch):
        def _boom(url, timeout):
            raise OSError("offline")

        monkeypatch.setattr(bootstrap.requests, "get", _boom)
        urls = bootstrap._exiftool_download_urls()
        assert urls
        assert all(url.startswith("https://sourceforge.net/projects/exiftool/files/")
                   for url in urls)
        assert all(url.endswith("_64.zip/download") for url in urls)

    def test_garbage_version_is_ignored(self, monkeypatch):
        class _FakeResp:
            text = "<html>error</html>"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(bootstrap.requests, "get",
                            lambda url, timeout: _FakeResp())
        urls = bootstrap._exiftool_download_urls()
        assert urls[0].startswith(
            "https://sourceforge.net/projects/exiftool/files/exiftool-13.59"
        )


class TestExiftoolExpectedSha256:
    def test_parses_sha2_line(self, monkeypatch):
        class _FakeResp:
            text = (
                "SHA2-256(exiftool-13.59_64.zip)= "
                "44b512b25af500724ba579d0a53c8fc5851628b692dd5e5d94ae4a15c2cba9ec\n"
                "SHA1(exiftool-13.59_64.zip)= 022b902bb3d01b171d5108e2c4be59491eb64444\n"
            )
        monkeypatch.setattr(bootstrap.requests, "get", lambda url, timeout: _FakeResp())
        url = ("https://sourceforge.net/projects/exiftool/files/"
               "exiftool-13.59_64.zip/download")
        assert bootstrap._exiftool_expected_sha256(url) == (
            "44b512b25af500724ba579d0a53c8fc5851628b692dd5e5d94ae4a15c2cba9ec")

    def test_returns_none_when_checksum_fetch_fails(self, monkeypatch):
        def _boom(url, timeout):
            raise OSError("offline")
        monkeypatch.setattr(bootstrap.requests, "get", _boom)
        url = ("https://sourceforge.net/projects/exiftool/files/"
               "exiftool-13.59_64.zip/download")
        assert bootstrap._exiftool_expected_sha256(url) is None

    def test_returns_none_when_version_missing(self):
        url = "https://sourceforge.net/projects/exiftool/files/exiftool-64.zip/download"
        assert bootstrap._exiftool_expected_sha256(url) is None

    def test_returns_none_when_line_missing(self, monkeypatch):
        class _FakeResp:
            text = "SHA1(exiftool-13.59_64.zip)= abc\n"
        monkeypatch.setattr(bootstrap.requests, "get", lambda url, timeout: _FakeResp())
        url = ("https://sourceforge.net/projects/exiftool/files/"
               "exiftool-13.59_64.zip/download")
        assert bootstrap._exiftool_expected_sha256(url) is None


class TestIsValidZip:
    def test_real_zip_returns_true(self, tmp_path):
        path = tmp_path / "test.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("exiftool(-k).exe", b"MZ...")
        assert bootstrap._is_valid_zip(path) is True

    def test_html_returns_false(self, tmp_path):
        path = tmp_path / "fake.zip"
        path.write_text("<html>404</html>", encoding="utf-8")
        assert bootstrap._is_valid_zip(path) is False

    def test_missing_file_returns_false(self, tmp_path):
        assert bootstrap._is_valid_zip(tmp_path / "nope.zip") is False


class TestExtractExiftool:
    def test_extracts_exe_and_files_folder(self, tmp_path, monkeypatch):
        extract_dir = tmp_path / "out"
        BIN_DIR = tmp_path / "bin"
        exe_data = b"MZ fake exe payload"
        files_txt = b"cpan needed by exiftool"

        zip_path = tmp_path / "exiftool.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("exiftool-13.59/exiftool(-k).exe", exe_data)
            zf.writestr("exiftool-13.59/exiftool_files/ExifTool_config", files_txt)

        monkeypatch.setattr(bootstrap, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(bootstrap, "BIN_DIR", BIN_DIR)

        assert bootstrap._extract_exiftool(zip_path) is True
        assert (BIN_DIR / "exiftool.exe").read_bytes() == exe_data
        assert (BIN_DIR / "exiftool_files" / "ExifTool_config").read_bytes() == files_txt
