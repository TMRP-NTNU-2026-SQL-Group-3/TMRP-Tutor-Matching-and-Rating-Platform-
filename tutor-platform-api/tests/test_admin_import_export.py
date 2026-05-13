"""Admin import / export endpoint tests (SEC-9).

Covers:
  POST /api/admin/import/{table_name}   — single-table CSV upload
  GET  /api/admin/export/{table_name}   — single-table CSV download
  POST /api/admin/import-all            — ZIP bulk import, including clear_first=True
  GET  /api/admin/export-all            — ZIP bulk export

Key invariants tested:
  - EXPORT_DENYLIST: the `users` table must be refused on export (400).
  - clear_first=True path on import-all is accepted and forwarded to the service.
  - Content-Type enforcement on single-table CSV import (415 on wrong type).
  - Content-Type enforcement on bulk ZIP import (415 on wrong type).
  - Admin role is required on every endpoint (403 for non-admin).

AdminImportService is patched at its construction site in
app.admin.api.dependencies. Export endpoints return FileResponse; a real
temporary file is created so FastAPI can stream it during the test.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

_IMPORT_SERVICE = "app.admin.api.dependencies.AdminImportService"
_CSRF = "test-csrf-token"


def _ah(admin_headers):
    return {**admin_headers, "X-CSRF-Token": _CSRF}


def _ck():
    return {"csrf_token": _CSRF}


class TestImportCsv:
    def test_admin_can_import_valid_csv(self, client, admin_headers, mock_conn):
        """Admin can upload a CSV for a permitted table and receives row count."""
        with patch(_IMPORT_SERVICE) as MockService:
            MockService.return_value.import_single_csv.return_value = 3

            resp = client.post(
                "/api/admin/import/subjects",
                files={"file": ("subjects.csv", b"subject_id,subject_name\n1,Math\n", "text/csv")},
                headers=_ah(admin_headers),
                cookies=_ck(),
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["count"] == 3

    def test_wrong_content_type_returns_415(self, client, admin_headers, mock_conn):
        """Non-CSV Content-Type is rejected before the service is called."""
        with patch(_IMPORT_SERVICE):
            resp = client.post(
                "/api/admin/import/subjects",
                files={"file": ("data.json", b'[{"x":1}]', "application/json")},
                headers=_ah(admin_headers),
                cookies=_ck(),
            )

        assert resp.status_code == 415

    def test_disallowed_table_returns_400(self, client, admin_headers, mock_conn):
        """Importing into a table not in ALLOWED_TABLES returns 400."""
        with patch(_IMPORT_SERVICE):
            resp = client.post(
                "/api/admin/import/nonexistent_table",
                files={"file": ("x.csv", b"col\nval\n", "text/csv")},
                headers=_ah(admin_headers),
                cookies=_ck(),
            )

        assert resp.status_code == 400

    def test_empty_csv_returns_zero_count(self, client, admin_headers, mock_conn):
        """A header-only CSV file results in count=0 without an error."""
        with patch(_IMPORT_SERVICE) as MockService:
            MockService.return_value.import_single_csv.return_value = 0

            resp = client.post(
                "/api/admin/import/subjects",
                files={"file": ("empty.csv", b"subject_id,subject_name\n", "text/csv")},
                headers=_ah(admin_headers),
                cookies=_ck(),
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["count"] == 0

    def test_non_admin_returns_403(self, client, parent_headers, mock_conn):
        """Non-admin callers are rejected before the service is consulted."""
        resp = client.post(
            "/api/admin/import/subjects",
            files={"file": ("x.csv", b"col\nval\n", "text/csv")},
            headers={**parent_headers, "X-CSRF-Token": _CSRF},
            cookies=_ck(),
        )
        assert resp.status_code == 403


class TestExportCsv:
    def test_admin_can_export_permitted_table(self, client, admin_headers, mock_conn):
        """Admin can download a CSV for any table not in EXPORT_DENYLIST."""
        with (
            tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f,
        ):
            f.write("subject_id,subject_name\n1,Math\n")
            tmp = f.name
        try:
            with patch(_IMPORT_SERVICE) as MockService:
                MockService.return_value.export_table_to_csv.return_value = Path(tmp)

                resp = client.get(
                    "/api/admin/export/subjects",
                    headers=admin_headers,
                )

            assert resp.status_code == 200
            assert "text/csv" in resp.headers.get("content-type", "")
        finally:
            os.unlink(tmp)

    def test_users_table_is_denylist_blocked(self, client, admin_headers, mock_conn):
        """EXPORT_DENYLIST: the users table must never be downloadable (contains password_hash)."""
        with patch(_IMPORT_SERVICE):
            resp = client.get(
                "/api/admin/export/users",
                headers=admin_headers,
            )

        assert resp.status_code == 400

    def test_nonexistent_table_returns_400(self, client, admin_headers, mock_conn):
        resp = client.get("/api/admin/export/not_a_table", headers=admin_headers)
        assert resp.status_code == 400

    def test_non_admin_returns_403(self, client, parent_headers, mock_conn):
        resp = client.get("/api/admin/export/subjects", headers=parent_headers)
        assert resp.status_code == 403


class TestImportAll:
    ENDPOINT = "/api/admin/import-all"

    def test_admin_can_bulk_import_zip(self, client, admin_headers, mock_conn):
        """Admin uploads a ZIP archive and receives an import summary."""
        with patch(_IMPORT_SERVICE) as MockService:
            MockService.return_value.import_zip.return_value = {
                "imported": {"subjects": 5, "tutors": 2},
                "errors": {},
            }

            resp = client.post(
                self.ENDPOINT,
                files={"file": ("all.zip", b"PK\x03\x04", "application/zip")},
                headers=_ah(admin_headers),
                cookies=_ck(),
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["imported"]["subjects"] == 5

    def test_clear_first_flag_is_forwarded_to_service(self, client, admin_headers, mock_conn):
        """clear_first=True path calls import_zip with the flag set."""
        with patch(_IMPORT_SERVICE) as MockService:
            MockService.return_value.import_zip.return_value = {
                "imported": {},
                "errors": {},
            }

            resp = client.post(
                f"{self.ENDPOINT}?clear_first=true",
                files={"file": ("all.zip", b"PK\x03\x04", "application/zip")},
                headers=_ah(admin_headers),
                cookies=_ck(),
            )

        assert resp.status_code == 200
        _, kwargs = MockService.return_value.import_zip.call_args
        assert kwargs.get("clear_first") is True

    def test_partial_errors_are_reported(self, client, admin_headers, mock_conn):
        """Import errors are surfaced in the response alongside the success count."""
        with patch(_IMPORT_SERVICE) as MockService:
            MockService.return_value.import_zip.return_value = {
                "imported": {"subjects": 2},
                "errors": {"tutors": ["row 3: duplicate key"]},
            }

            resp = client.post(
                self.ENDPOINT,
                files={"file": ("all.zip", b"PK\x03\x04", "application/zip")},
                headers=_ah(admin_headers),
                cookies=_ck(),
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "errors" in data

    def test_wrong_content_type_returns_415(self, client, admin_headers, mock_conn):
        """Non-ZIP Content-Type is rejected before the service is called."""
        with patch(_IMPORT_SERVICE):
            resp = client.post(
                self.ENDPOINT,
                files={"file": ("all.tar.gz", b"\x1f\x8b", "application/gzip")},
                headers=_ah(admin_headers),
                cookies=_ck(),
            )

        assert resp.status_code == 415

    def test_non_admin_returns_403(self, client, parent_headers, mock_conn):
        resp = client.post(
            self.ENDPOINT,
            files={"file": ("all.zip", b"PK\x03\x04", "application/zip")},
            headers={**parent_headers, "X-CSRF-Token": _CSRF},
            cookies=_ck(),
        )
        assert resp.status_code == 403


class TestExportAll:
    ENDPOINT = "/api/admin/export-all"

    def test_admin_can_download_all_tables_as_zip(self, client, admin_headers, mock_conn):
        """Admin receives a ZIP archive of all exportable tables."""
        with (
            tempfile.NamedTemporaryFile(mode="wb", suffix=".zip", delete=False) as f,
        ):
            f.write(b"PK\x05\x06" + b"\x00" * 18)
            tmp = f.name
        try:
            with patch(_IMPORT_SERVICE) as MockService:
                MockService.return_value.export_all_tables_to_zip.return_value = Path(tmp)

                resp = client.get(self.ENDPOINT, headers=admin_headers)

            assert resp.status_code == 200
            assert "zip" in resp.headers.get("content-type", "")
        finally:
            os.unlink(tmp)

    def test_non_admin_returns_403(self, client, parent_headers, mock_conn):
        resp = client.get(self.ENDPOINT, headers=parent_headers)
        assert resp.status_code == 403
