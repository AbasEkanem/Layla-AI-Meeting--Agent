"""Dex's Gmail rendering helpers: draft-prefix stripping (approval-gate hygiene)
and MIME assembly (headers + a plain/html alternative pair)."""

from subagent_config.dex._gmail import _md_to_html, build_mime, strip_draft_prefix


def test_strip_draft_prefix_variants():
    assert strip_draft_prefix("[DRAFT] Follow-up") == "Follow-up"
    assert strip_draft_prefix("[draft]   Spaced") == "Spaced"
    assert strip_draft_prefix("  [DRAFT] Leading ws") == "Leading ws"
    assert strip_draft_prefix("No prefix here") == "No prefix here"
    # Only a leading token is stripped, never one mid-subject.
    assert strip_draft_prefix("Re: [DRAFT] x") == "Re: [DRAFT] x"


def test_build_mime_headers_and_alternative_parts():
    msg = build_mime(to="a@x.com", subject="Hello", body="Body", bcc="b@x.com", cc="c@x.com")
    assert msg["To"] == "a@x.com"
    assert msg["Subject"] == "Hello"
    assert msg["Bcc"] == "b@x.com"
    assert msg["Cc"] == "c@x.com"
    assert msg.get_content_type() == "multipart/alternative"
    types = sorted(p.get_content_type() for p in msg.get_payload())
    assert types == ["text/html", "text/plain"]


def test_md_to_html_renders_heading_bullet_bold():
    html = _md_to_html("# Title\n- item one\n**bold**")
    assert "<h1" in html
    assert "<ul" in html and "<li" in html
    assert "<strong>bold</strong>" in html
