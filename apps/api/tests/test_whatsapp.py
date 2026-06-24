"""Unit tests for the WhatsApp pure layers: signature, parser, conversation.

No DB or HTTP — the service/router DB paths are covered by the integration
harness. These lock down the security-critical signature check, the Meta payload
parser, and the full conversation walk to an EnqueueCapture action.
"""

from __future__ import annotations

import hashlib
import hmac

from victus_api.whatsapp import meta
from victus_api.whatsapp.conversation import (
    AUDIT_QUESTIONS,
    ConvState,
    EnqueueCapture,
    SessionData,
    advance,
    start_session,
)

# --- signature ---------------------------------------------------------------


def test_signature_accepts_valid_and_rejects_tampered() -> None:
    secret = "topsecret"
    body = b'{"object":"whatsapp_business_account"}'
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert meta.verify_signature(
        app_secret=secret, raw_body=body, signature_header=f"sha256={digest}"
    )
    # Tampered body
    assert not meta.verify_signature(
        app_secret=secret, raw_body=body + b"x", signature_header=f"sha256={digest}"
    )
    # Missing / malformed header
    assert not meta.verify_signature(
        app_secret=secret, raw_body=body, signature_header=None
    )
    assert not meta.verify_signature(
        app_secret=secret, raw_body=body, signature_header=digest
    )


# --- parser ------------------------------------------------------------------


def _envelope(message: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [
                                {"wa_id": "263771234567", "profile": {"name": "Tendai"}}
                            ],
                            "messages": [message],
                        }
                    }
                ]
            }
        ],
    }


def test_parse_text_message() -> None:
    payload = _envelope(
        {"from": "263771234567", "id": "wamid.1", "type": "text", "text": {"body": "hi"}}
    )
    msgs = meta.parse_inbound(payload)
    assert len(msgs) == 1
    assert msgs[0].text == "hi"
    assert msgs[0].profile_name == "Tendai"
    assert msgs[0].media_id is None


def test_parse_video_message() -> None:
    payload = _envelope(
        {"from": "263771234567", "id": "wamid.2", "type": "video", "video": {"id": "MEDIA42"}}
    )
    msgs = meta.parse_inbound(payload)
    assert msgs[0].type == "video"
    assert msgs[0].media_id == "MEDIA42"


def test_parse_status_callback_is_empty() -> None:
    # Delivery/read receipts carry no "messages" — must yield nothing.
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"id": "x"}]}}]}]}
    assert meta.parse_inbound(payload) == []


# --- conversation walk -------------------------------------------------------


def _say(session: SessionData, text=None, *, video=False, media_id=None):
    return advance(session, text=text, has_video=video, media_id=media_id)


def test_full_walk_to_enqueue() -> None:
    s = SessionData(phone="263771234567")
    assert s.state is ConvState.LANGUAGE

    _say(s, "1")  # English
    assert s.state is ConvState.CONSENT and s.language == "en"

    _say(s, "yes")
    assert s.state is ConvState.AGE

    # Invalid age re-prompts without advancing.
    _say(s, "abc")
    assert s.state is ConvState.AGE
    _say(s, "42")
    assert s.state is ConvState.SEX and s.intake["age_years"] == 42

    _say(s, "2")  # Female
    assert s.state is ConvState.HEIGHT and s.intake["sex"] == "FEMALE"

    _say(s, "170")
    assert s.state is ConvState.WEIGHT and s.intake["height_cm"] == 170
    _say(s, "72")
    assert s.state is ConvState.WAIST and s.intake["weight_kg"] == 72
    _say(s, "88")
    assert s.state is ConvState.AUDIT and s.intake["waist_cm"] == 88

    # Answer the 6 audit questions: yes to the first (a safety trigger), no rest.
    for i in range(len(AUDIT_QUESTIONS)):
        _say(s, "yes" if i == 0 else "no")
    assert s.state is ConvState.VIDEO
    assert AUDIT_QUESTIONS[0]["key"] in s.safety_triggers

    # Text instead of a video re-prompts.
    turn = _say(s, "here you go")
    assert s.state is ConvState.VIDEO and turn.action is None

    # The video triggers the enqueue action.
    turn = _say(s, video=True, media_id="MEDIA99")
    assert s.state is ConvState.COMPLETE
    assert isinstance(turn.action, EnqueueCapture)
    assert turn.action.media_id == "MEDIA99"
    assert turn.action.language == "en"
    inputs = turn.action.intake["inputs"]
    assert inputs == {
        "age_years": 42,
        "sex": "FEMALE",
        "height_cm": 170,
        "weight_kg": 72,
        "waist_cm": 88,
    }
    assert AUDIT_QUESTIONS[0]["key"] in turn.action.intake["symptoms"]["safety_triggers"]


def test_consent_decline_ends_flow() -> None:
    s = SessionData(phone="263770000000")
    _say(s, "1")
    turn = _say(s, "no")
    assert s.state is ConvState.DECLINED
    assert "won't collect" in turn.replies[0].lower()


# --- site-aware language menu ------------------------------------------------


def test_nigeria_menu_offers_nigerian_languages() -> None:
    _, turn = start_session("2348010000000", "NG")
    menu = turn.replies[0]
    for label in ("English", "Yor", "Igbo", "Hausa", "Naij"):
        assert label in menu
    # Zimbabwe languages must not appear on a Nigeria instance.
    assert "Shona" not in menu and "Ndebele" not in menu


def test_nigeria_digits_map_to_nigerian_languages() -> None:
    # On NG, "2" is Yoruba (not Shona); 3/4/5 cover Igbo/Hausa/Pidgin.
    for digit, code in (("2", "yo"), ("3", "ig"), ("4", "ha"), ("5", "pcm")):
        s = SessionData(phone="2348010000001")
        advance(s, text=digit, has_video=False, site_code="NG")
        assert s.language == code and s.state is ConvState.CONSENT


def test_zimbabwe_menu_unchanged() -> None:
    _, turn = start_session("263770000001", "ZW")
    assert "Shona" in turn.replies[0] and "Ndebele" in turn.replies[0]
    for digit, code in (("2", "sn"), ("3", "nd")):
        s = SessionData(phone="263770000002")
        advance(s, text=digit, has_video=False, site_code="ZW")
        assert s.language == code


def test_unknown_site_keeps_default_menu() -> None:
    # No site (e.g. the dev default) keeps the original English/Shona/Ndebele.
    _, turn = start_session("100000000")
    assert "Shona" in turn.replies[0]
    s = SessionData(phone="100000001")
    advance(s, text="2", has_video=False)  # no site_code
    assert s.language == "sn"


def test_alias_only_accepted_when_site_offers_it() -> None:
    # "yoruba" is valid on NG, rejected on ZW (re-prompts, stays in LANGUAGE).
    ng = SessionData(phone="2348010000003")
    advance(ng, text="yoruba", has_video=False, site_code="NG")
    assert ng.language == "yo" and ng.state is ConvState.CONSENT

    zw = SessionData(phone="263770000003")
    advance(zw, text="yoruba", has_video=False, site_code="ZW")
    assert zw.language is None and zw.state is ConvState.LANGUAGE


def test_nigerian_language_prompts_fall_back_to_english() -> None:
    # Choosing Yoruba records the language; conversational copy is English until
    # translated (the consent prompt is the authoritative English text).
    s = SessionData(phone="2348010000004")
    turn = advance(s, text="2", has_video=False, site_code="NG")  # Yoruba
    assert s.language == "yo"
    assert "consent" in turn.replies[0].lower()


def test_restart_from_complete() -> None:
    s = SessionData(phone="263770000001", state=ConvState.COMPLETE)
    turn = _say(s, "start")
    assert s.state is ConvState.LANGUAGE
    assert "language" in turn.replies[0].lower()


def test_stop_command_flags_purge_from_any_state() -> None:
    # Mid-flow, with PII already collected — STOP signals a purge.
    s = SessionData(phone="263771230000", state=ConvState.WEIGHT)
    s.intake["age_years"] = 50
    turn = _say(s, "STOP")
    assert turn.purge is True
    assert "deleted" in turn.replies[0].lower()

    # Synonyms, case-insensitive, from any state.
    for word in ("delete", "Cancel", "remove"):
        assert _say(SessionData(phone="x", state=ConvState.AGE), word).purge is True

    # A normal answer never purges.
    assert _say(SessionData(phone="y", state=ConvState.AGE), "42").purge is False
