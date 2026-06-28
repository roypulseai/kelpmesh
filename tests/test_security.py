"""Tests for encryption, secrets scanning, data leak prevention, and telemetry guard."""

import os
import sys
from pathlib import Path

import pytest

from briq.core.crypto import encrypt_file, decrypt_file, is_encrypted, generate_key
from briq.state.engine import StateEngine
from briq.cli.scan import scan_file, SCAN_PATTERNS
from briq.core.executor import Executor, _EXTERNAL_URL_RE, _EXTERNAL_DB_RE


class TestCrypto:
    def test_generate_key_is_valid(self):
        key = generate_key()
        assert isinstance(key, str)
        assert len(key) > 20

    def test_encrypt_then_decrypt_roundtrip(self, tmp_path: Path):
        data = b"hello briq state data"
        f = tmp_path / "test.bin"
        f.write_bytes(data)
        old_key = os.environ.get("BRIQ_ENCRYPTION_KEY")
        try:
            os.environ["BRIQ_ENCRYPTION_KEY"] = generate_key()
            assert encrypt_file(f)
            raw = f.read_bytes()
            assert is_encrypted(raw)
            decrypted = decrypt_file(f)
            assert decrypted == data
        finally:
            if old_key:
                os.environ["BRIQ_ENCRYPTION_KEY"] = old_key
            else:
                os.environ.pop("BRIQ_ENCRYPTION_KEY", None)

    def test_is_encrypted_false_on_plaintext(self):
        assert not is_encrypted(b"plain text data")

    def test_decrypt_wrong_key_returns_none(self, tmp_path: Path):
        data = b"sensitive state data"
        f = tmp_path / "test.bin"
        f.write_bytes(data)
        os.environ["BRIQ_ENCRYPTION_KEY"] = generate_key()
        encrypt_file(f)
        os.environ["BRIQ_ENCRYPTION_KEY"] = generate_key()  # different key
        result = decrypt_file(f)
        assert result is None


class TestStateEngineEncryption:
    def test_encrypted_state_roundtrip(self, tmp_path: Path):
        key = generate_key()
        old_key = os.environ.get("BRIQ_ENCRYPTION_KEY")
        try:
            os.environ["BRIQ_ENCRYPTION_KEY"] = key
            state = StateEngine(tmp_path)
            state.record_run("model_a", "hash_1", row_count=100)
            state.close()

            db_path = tmp_path / "target" / "briq_state.duckdb"
            assert db_path.exists()
            raw = db_path.read_bytes()
            assert is_encrypted(raw)

            state2 = StateEngine(tmp_path)
            assert state2.is_up_to_date("model_a", "hash_1")
            assert not state2.is_up_to_date("model_a", "wrong_hash")
            state2.close()
        finally:
            if old_key:
                os.environ["BRIQ_ENCRYPTION_KEY"] = old_key
            else:
                os.environ.pop("BRIQ_ENCRYPTION_KEY", None)

    def test_no_encryption_when_no_key(self, tmp_path: Path):
        old_key = os.environ.pop("BRIQ_ENCRYPTION_KEY", None)
        try:
            state = StateEngine(tmp_path)
            state.record_run("m", "h")
            state.close()
            db_path = tmp_path / "target" / "briq_state.duckdb"
            raw = db_path.read_bytes()
            assert not is_encrypted(raw)
        finally:
            if old_key:
                os.environ["BRIQ_ENCRYPTION_KEY"] = old_key


class TestSecretsScanner:
    def _scan(self, sql: str, patterns=None):
        p = Path.cwd().resolve() / "test_scan.sql"
        p.write_text(sql, encoding="utf-8")
        try:
            return scan_file(p, patterns=patterns)
        finally:
            p.unlink(missing_ok=True)

    def test_detects_password(self):
        results = self._scan(
            "SELECT * FROM users WHERE password = 'supersecret123'",
            patterns=[SCAN_PATTERNS[0]],
        )
        assert len(results) == 1
        assert results[0]["type"] == "password"

    def test_detects_api_key(self):
        results = self._scan(
            "CREATE SECRET api_key = 'sk_live_AbCdEfGhIjKlMnOp'",
            patterns=[SCAN_PATTERNS[2]],
        )
        assert len(results) == 1
        assert results[0]["type"] == "api_key"

    def test_detects_pem_key(self):
        results = self._scan(
            "-----BEGIN RSA PRIVATE KEY-----\nYWJjZGVmZw==\n-----END RSA PRIVATE KEY-----",
            patterns=[SCAN_PATTERNS[7]],
        )
        assert len(results) >= 1

    def test_detects_postgres_url(self):
        results = self._scan(
            "postgresql://user:secret@host:5432/db",
            patterns=[SCAN_PATTERNS[9]],
        )
        assert len(results) == 1

    def test_detects_jdbc_url(self):
        results = self._scan(
            "jdbc:postgresql://host:5432/db?user=admin&password=p@ss",
            patterns=[SCAN_PATTERNS[8]],
        )
        assert len(results) == 1

    def test_ignore_comment_suppresses(self):
        results = self._scan(
            "SELECT * FROM users WHERE password = 'secret'  -- briq:scan-ignore"
        )
        pw_results = [r for r in results if r["type"] == "password"]
        assert len(pw_results) == 0

    def test_clean_sql_returns_empty(self):
        results = self._scan("SELECT id, name FROM customers WHERE status = 'active'")
        assert len(results) == 0

    def test_detects_env_var_fallback(self):
        results = self._scan(
            "SELECT {{ env_var('DB_PASS', 'hardcoded_fallback_value') }}"
        )
        env_results = [r for r in results if r["type"] == "env_fallback"]
        assert len(env_results) == 1


class TestDataLeakPrevention:
    def test_url_re_matches_https(self):
        assert _EXTERNAL_URL_RE.search("read_csv_auto('https://evil.com/data.csv')")

    def test_url_re_matches_s3(self):
        assert _EXTERNAL_URL_RE.search("FROM read_parquet('s3://bucket/key')")

    def test_url_re_matches_gs(self):
        assert _EXTERNAL_URL_RE.search("FROM read_json('gs://bucket/key')")

    def test_db_re_matches_read_csv(self):
        assert _EXTERNAL_DB_RE.search("read_csv('file.csv')")

    def test_db_re_matches_postgresql(self):
        assert _EXTERNAL_DB_RE.search("postgresql('host=...')")

    def test_clean_sql_no_match_url(self):
        assert not _EXTERNAL_URL_RE.search("SELECT * FROM orders")
        assert not _EXTERNAL_DB_RE.search("SELECT * FROM orders")


class TestTelemetryGuard:
    def test_validate_no_telemetry_blocks_known_pkgs(self):
        from briq.cli.main import _validate_no_telemetry
        sys.modules["posthog"] = type(sys)("posthog")
        with pytest.raises(SystemExit):
            _validate_no_telemetry()
        sys.modules.pop("posthog", None)

    def test_validate_no_telemetry_passes_clean(self):
        from briq.cli.main import _validate_no_telemetry
        for pkg in ["http", "json", "os"]:
            sys.modules.pop(pkg, None)
        _validate_no_telemetry()
