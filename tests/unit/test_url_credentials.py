"""Tier 1 unit tests for URL credential decode helpers.

Tests null-byte rejection, normal decode, edge cases, and
pre-encoding of special characters in passwords.

Ref: T-13-07, rules/security.md Credential Decode Helpers
"""

from urllib.parse import urlparse

import pytest

from midas.utils.url_credentials import (
    decode_userinfo_or_raise,
    preencode_password_special_chars,
)


# ---------------------------------------------------------------------------
# decode_userinfo_or_raise
# ---------------------------------------------------------------------------


class TestDecodeUserinfo:
    """decode_userinfo_or_raise: extract and validate URL credentials."""

    def test_normal_credentials_decoded(self):
        """Normal username:password in URL are decoded correctly."""
        parsed = urlparse("postgresql://myuser:mypass@db.host:5432/mydb")
        user, password = decode_userinfo_or_raise(parsed)
        assert user == "myuser"
        assert password == "mypass"

    def test_percent_encoded_password_decoded(self):
        """Percent-encoded special characters in password are decoded."""
        parsed = urlparse("mysql://admin:p%40ssw0rd@db.example.com/mydb")
        user, password = decode_userinfo_or_raise(parsed)
        assert user == "admin"
        assert password == "p@ssw0rd"

    def test_percent_encoded_username_decoded(self):
        """Percent-encoded username is decoded."""
        parsed = urlparse("redis://user%40domain:secret@cache:6379/0")
        user, password = decode_userinfo_or_raise(parsed)
        assert user == "user@domain"
        assert password == "secret"

    def test_no_username_returns_empty_user(self):
        """URL with no username returns empty string for user."""
        parsed = urlparse("redis://:passwordonly@cache:6379/0")
        user, password = decode_userinfo_or_raise(parsed)
        assert user == ""
        assert password == "passwordonly"

    def test_no_password_returns_empty_pass(self):
        """URL with no password returns empty string for password."""
        parsed = urlparse("postgresql://useronly@db.host/mydb")
        user, password = decode_userinfo_or_raise(parsed)
        assert user == "useronly"
        assert password == ""

    def test_null_byte_in_password_raises(self):
        """Null byte in password after percent-decode raises ValueError."""
        parsed = urlparse("mysql://user:%00bypass@host/db")
        with pytest.raises(ValueError, match="[Nn]ull byte"):
            decode_userinfo_or_raise(parsed)

    def test_null_byte_in_username_raises(self):
        """Null byte in username after percent-decode raises ValueError."""
        parsed = urlparse("mysql://user%00admin:pass@host/db")
        with pytest.raises(ValueError, match="[Nn]ull byte"):
            decode_userinfo_or_raise(parsed)

    def test_empty_url_returns_empty_creds(self):
        """URL with no userinfo returns empty strings."""
        parsed = urlparse("postgresql://db.host:5432/mydb")
        user, password = decode_userinfo_or_raise(parsed)
        assert user == ""
        assert password == ""

    def test_urlencoded_null_in_password_raises(self):
        """Multiple null bytes in password all raise."""
        parsed = urlparse("mysql://admin:p%00a%00s%00s@host/db")
        with pytest.raises(ValueError, match="[Nn]ull byte"):
            decode_userinfo_or_raise(parsed)

    def test_complex_password_with_special_chars(self):
        """Password with many special characters decodes correctly."""
        parsed = urlparse("postgresql://admin:p%40ss%3Aw%23rd%2Fp%3Fth@db.host/mydb")
        user, password = decode_userinfo_or_raise(parsed)
        assert user == "admin"
        assert password == "p@ss:w#rd/p?th"


# ---------------------------------------------------------------------------
# preencode_password_special_chars
# ---------------------------------------------------------------------------


class TestPreencodePasswordSpecialChars:
    """preencode_password_special_chars: encode special chars in passwords."""

    def test_at_sign_encoded(self):
        """@ in password is percent-encoded and result is parseable."""
        url = "postgresql://user:p@ssword@db.host/mydb"
        result = preencode_password_special_chars(url)
        assert "%40" in result
        parsed = urlparse(result)
        assert parsed.hostname == "db.host"

    def test_colon_in_password_encoded(self):
        """Colon in password is percent-encoded."""
        url = "mysql://user:pass:word@db.host:3306/mydb"
        result = preencode_password_special_chars(url)
        assert "%3A" in result
        parsed = urlparse(result)
        assert parsed.hostname == "db.host"

    def test_no_password_returns_unchanged(self):
        """URL with no password returns unchanged."""
        url = "postgresql://useronly@db.host/mydb"
        result = preencode_password_special_chars(url)
        assert result == url

    def test_plain_password_returns_same_url(self):
        """Password with no special characters returns the same URL."""
        url = "postgresql://admin:plainpassword@db.host/mydb"
        result = preencode_password_special_chars(url)
        assert result == url

    def test_result_is_parseable(self):
        """Result of pre-encoding can be parsed by urlparse."""
        # Use a URL where @ and : in the password are the ones the function handles
        url = "postgresql://admin:p@ssword@db.host/mydb"
        result = preencode_password_special_chars(url)
        parsed = urlparse(result)
        # Should parse without crashing and have a hostname
        assert parsed.hostname == "db.host"
