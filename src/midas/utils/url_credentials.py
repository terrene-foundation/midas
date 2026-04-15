"""
URL credential decode helpers with null-byte protection.

Shared helper for all connection-string parsing sites. Rejects null bytes
after percent-decoding, preventing credential truncation attacks.

Ref: T-13-07, rules/security.md § Credential Decode Helpers
"""

from urllib.parse import unquote, urlparse


def decode_userinfo_or_raise(parsed) -> tuple[str, str]:
    """Extract and percent-decode username/password from a urlparse result.

    Rejects null bytes after decoding.

    Returns:
        (username, password) tuple.

    Raises:
        ValueError: If null bytes are found in decoded credentials.
    """
    raw_user = parsed.username or ""
    raw_pass = parsed.password or ""

    user = unquote(raw_user)
    password = unquote(raw_pass)

    if "\x00" in user:
        raise ValueError(
            "Null byte found in URL username after percent-decode. "
            "This may be a credential truncation attack."
        )
    if "\x00" in password:
        raise ValueError(
            "Null byte found in URL password after percent-decode. "
            "This may be a credential truncation attack."
        )

    return user, password


def preencode_password_special_chars(url: str) -> str:
    """Pre-encode special characters in the password portion of a URL.

    Ensures characters like @, :, #, ?, / in passwords are properly
    percent-encoded for safe transit through URL parsers.
    """
    parsed = urlparse(url)
    if not parsed.password:
        return url

    password = parsed.password
    # Encode characters that confuse URL parsing
    special = {"@": "%40", ":": "%3A", "#": "%23", "?": "%3F", "/": "%2F"}
    encoded = password
    for char, replacement in special.items():
        encoded = encoded.replace(char, replacement)

    # Reconstruct URL
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc += f":{parsed.port}"
    user = parsed.username or ""
    netloc = f"{user}:{encoded}@{netloc}"

    return parsed._replace(netloc=netloc).geturl()
