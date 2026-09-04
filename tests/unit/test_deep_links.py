from pex_bridge.deep_links import devin_session_url, safe_external_url


def test_safe_external_url_allows_only_existing_devin_sessions():
    assert (
        safe_external_url("https://app.devin.ai/sessions/devin-1")
        == "https://app.devin.ai/sessions/devin-1"
    )
    assert safe_external_url("http://app.devin.ai/sessions/devin-1") is None
    assert safe_external_url("javascript:alert(1)") is None
    assert safe_external_url("https://evil.example/sessions/devin-1") is None
    assert safe_external_url("https://app.devin.ai/sessions/devin-1?next=https://evil") is None
    assert safe_external_url("https://user:pass@app.devin.ai/sessions/devin-1") is None
    assert safe_external_url("https://app.devin.ai/sessions/../other") is None
    assert safe_external_url("https://app.devin.ai/sessions/new") is None


def test_devin_session_url_ignores_untrusted_api_links_and_does_not_invent_hosts():
    assert (
        devin_session_url(vendor_id="devin-1")
        == "https://app.devin.ai/sessions/devin-1"
    )
    assert (
        devin_session_url(
            vendor_id="devin-1",
            provided="https://evil.example/sessions/devin-1",
        )
        == "https://app.devin.ai/sessions/devin-1"
    )
    assert (
        devin_session_url(
            vendor_id="devin-1",
            provided="https://app.devin.ai/sessions/devin-1",
        )
        == "https://app.devin.ai/sessions/devin-1"
    )
    assert devin_session_url(vendor_id="devin/1") is None
    assert devin_session_url(vendor_id="") is None
