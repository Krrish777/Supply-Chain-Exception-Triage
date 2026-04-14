"""Input sanitization tests (test-plan Area 3, tests 3.1–3.3)."""

from __future__ import annotations

from supply_chain_triage.middleware.input_sanitization import sanitize


class TestXSSStripping:
    def test_script_tag_is_stripped_or_escaped(self) -> None:
        # Given: input with <script> tag
        result = sanitize("<script>alert('x')</script>Hello")
        # Then: output either strips script entirely or HTML-escapes it; must not leave raw tag
        assert "<script>" not in result
        assert "alert" not in result or "&lt;" in result


class TestControlCharStripping:
    def test_control_chars_stripped_except_newline_cr_tab(self) -> None:
        # Given: input with NUL, SOH, STX + a newline + tab
        result = sanitize("hello\x00\x01\x02\n\there")
        # Then: bytes < 0x20 removed except \n \r \t
        for ch in result:
            assert ord(ch) >= 0x20 or ch in {"\n", "\r", "\t"}
        assert "\n" in result
        assert "\t" in result


class TestUnicodePreservation:
    def test_hindi_hinglish_unicode_preserved(self) -> None:
        # Given: Hindi input (India-first market requirement)
        original = "गाड़ी खराब हो गई"
        # When: sanitized
        result = sanitize(original)
        # Then: byte-for-byte preservation
        assert result == original
