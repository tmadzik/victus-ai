"""Pure conversation state machine for the WhatsApp check-up flow.

Walks a participant from first contact to a queued capture:

    LANGUAGE → CONSENT → AGE → SEX → HEIGHT → WEIGHT → WAIST
             → AUDIT (6 yes/no questions) → VIDEO → COMPLETE

It owns no I/O. ``advance`` takes the current :class:`SessionData` and a parsed
inbound message and returns the bot's reply(ies) plus an optional
:class:`EnqueueCapture` action (emitted when the video arrives). The service
layer persists the session and acts on the action. Invalid answers re-prompt
without advancing.

The collected fields map 1:1 onto ``TriageAssessmentRequest`` so the webhook can
run NCD-3B triage on the intake while the worker processes the video for vitals.

LOCALISATION: the language menu is *site-aware* — a Zimbabwe deployment offers
English/Shona/Ndebele, a Nigeria deployment English/Yoruba/Igbo/Hausa/Naija
(Nigerian Pidgin) — driven by the instance's ``site_code``. English prompts are
complete and authoritative; every other language currently falls back to English
for the conversational prompts and MUST be translated by a native clinical
speaker before real participant contact. The chosen language is still recorded
on the session and carried to the worker, so translations light up without code
changes. The *result*/*re-record* messages (worker.messages) are already
localised for the languages that have copy.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from victus_api.triage.schemas import Sex


class ConvState(str, enum.Enum):
    LANGUAGE = "LANGUAGE"
    CONSENT = "CONSENT"
    AGE = "AGE"
    SEX = "SEX"
    HEIGHT = "HEIGHT"
    WEIGHT = "WEIGHT"
    WAIST = "WAIST"
    AUDIT = "AUDIT"
    VIDEO = "VIDEO"
    COMPLETE = "COMPLETE"
    DECLINED = "DECLINED"
    # Kiosk-linked branch: the phone scanned a terminal QR, so it only needs to
    # grant consent — the capture happens at the kiosk, not over WhatsApp. Driven
    # by the WhatsApp service (it needs the DB), not the pure FSM.
    KIOSK_CONSENT = "KIOSK_CONSENT"


# Six-question behavioural/symptom audit. ``kind`` routes a "yes" into the
# triage SymptomAudit lists; safety keys can force a RED via the override layer.
AUDIT_QUESTIONS: tuple[dict[str, str], ...] = (
    {"key": "polydipsia_unquenchable_thirst", "kind": "safety",
     "q": "Do you feel a constant, unquenchable thirst?"},
    {"key": "polyuria_nocturia_severe", "kind": "safety",
     "q": "Are you urinating much more than usual, especially at night?"},
    {"key": "blurred_vision_progressive", "kind": "safety",
     "q": "Has your vision become blurred or worse recently?"},
    {"key": "chest_pain_radiating", "kind": "safety",
     "q": "Do you have chest pain that spreads to your arm, neck or jaw?"},
    {"key": "family_history_diabetes", "kind": "contextual",
     "q": "Does a parent or sibling have diabetes?"},
    {"key": "smoker_current", "kind": "contextual",
     "q": "Do you currently smoke tobacco?"},
)


@dataclass
class SessionData:
    """Mutable per-phone conversation state (persisted by the service)."""

    phone: str
    state: ConvState = ConvState.LANGUAGE
    language: str | None = None
    consent: bool = False
    intake: dict[str, Any] = field(default_factory=dict)
    audit_index: int = 0
    safety_triggers: list[str] = field(default_factory=list)
    contextual: list[str] = field(default_factory=list)

    def triage_request(self) -> dict[str, Any]:
        """Shape the collected fields as a ``TriageAssessmentRequest`` dict."""
        return {
            "inputs": {
                "age_years": self.intake.get("age_years"),
                "sex": self.intake.get("sex"),
                "height_cm": self.intake.get("height_cm"),
                "weight_kg": self.intake.get("weight_kg"),
                "waist_cm": self.intake.get("waist_cm"),
            },
            "symptoms": {
                "safety_triggers": list(self.safety_triggers),
                "contextual": list(self.contextual),
            },
        }


@dataclass(frozen=True)
class EnqueueCapture:
    """Action: a video arrived — queue it with the collected intake."""

    media_id: str
    language: str
    intake: dict[str, Any]


@dataclass(frozen=True)
class ConversationTurn:
    replies: list[str]
    action: EnqueueCapture | None = None
    # Signals the service to erase this phone's session + scrub its jobs (the
    # STOP/DELETE command). Pure FSM cannot touch the DB, so it just flags intent.
    purge: bool = False


# Global data-deletion command words (case-insensitive), honoured from any state.
PURGE_COMMANDS: frozenset[str] = frozenset({"stop", "delete", "cancel", "remove"})


# --- language menu (site-aware) ----------------------------------------------

# (digit, language code, display label) for one menu entry.
LanguageOption = tuple[str, str, str]


@dataclass(frozen=True)
class _LangMenu:
    lead_in: str
    options: tuple[LanguageOption, ...]


# Per-site language menus. A deployment shows only its country's languages.
_LANG_MENUS: dict[str, _LangMenu] = {
    "ZW": _LangMenu(
        "Choose a language / Sarudza mutauro / Khetha ulimi:",
        (
            ("1", "en", "English"),
            ("2", "sn", "Shona"),
            ("3", "nd", "Ndebele"),
        ),
    ),
    "NG": _LangMenu(
        "Choose a language:",
        (
            ("1", "en", "English"),
            ("2", "yo", "Yorùbá"),
            ("3", "ig", "Igbo"),
            ("4", "ha", "Hausa"),
            ("5", "pcm", "Naijá"),
        ),
    ),
}
# Unknown / unset site keeps the original English+Shona+Ndebele menu.
_DEFAULT_MENU = _LANG_MENUS["ZW"]

# Language-name aliases accepted in addition to the menu digit / code, restricted
# at parse time to the languages the site actually offers.
_LANG_ALIASES: dict[str, str] = {
    "english": "en",
    "shona": "sn",
    "chishona": "sn",
    "ndebele": "nd",
    "isindebele": "nd",
    "yoruba": "yo",
    "igbo": "ig",
    "hausa": "ha",
    "pidgin": "pcm",
    "naija": "pcm",
    "pcm": "pcm",
}


def _menu_for_site(site_code: str | None) -> _LangMenu:
    if not site_code:
        return _DEFAULT_MENU
    return _LANG_MENUS.get(site_code.strip().upper(), _DEFAULT_MENU)


def _welcome(site_code: str | None = None) -> str:
    menu = _menu_for_site(site_code)
    options = "   ".join(
        f"{digit}️⃣ {label}" for digit, _, label in menu.options
    )
    return (
        "👋 Welcome to *Victus* — a free, contactless wellness check-up.\n\n"
        f"{menu.lead_in}\n{options}"
    )


# --- prompt copy (English authoritative; see LOCALISATION note above) --------

_EN: dict[str, str] = {
    "consent": (
        "This is a *wellness screening, not a medical diagnosis*, and it is part "
        "of a research demonstrator. We'll ask a few health questions and a "
        "30-second video selfie to estimate your vitals. Your video is deleted "
        "right after analysis. Reply STOP at any time to delete your information.\n\n"
        "Do you consent to continue? (reply YES or NO)"
    ),
    "purged": (
        "🗑️ Done — your information and any pending analysis have been deleted. "
        "Reply START any time to begin a new check-up. Stay well."
    ),
    "declined": (
        "No problem — we won't collect anything. Reply START any time if you "
        "change your mind. Stay well."
    ),
    "age": "Great. How old are you? (years, e.g. 42)",
    "sex": "What is your sex? Reply 1 for Male, 2 for Female, 3 for Other.",
    "height": "Your height in centimetres? (e.g. 170)",
    "weight": "Your weight in kilograms? (e.g. 72)",
    "waist": "Your waist measurement in centimetres? (e.g. 88)",
    "video": (
        "Last step 📹 Record a *30-second* video selfie:\n"
        "• Face a window or bright light\n"
        "• Hold the phone steady at arm's length\n"
        "• Keep your whole face in view and stay still\n\n"
        "Send the video here when ready."
    ),
    "video_expected": "Please record and send a 30-second video selfie to finish.",
    "processing": (
        "Got it ✅ Analysing your video now — this takes a moment. "
        "Your results will arrive here shortly."
    ),
    "complete": "We're preparing your results. Reply START to do another check-up.",
    "retry_number": "Sorry, I didn't catch a valid number. {q}",
    "retry_choice": "Please reply with one of the options. {q}",
    "retry_yesno": "Please reply YES or NO. {q}",
}


def _t(key: str, lang: str | None, **fmt: str) -> str:
    # Shona/Ndebele fall back to English until translated (see module note).
    text = _EN[key]
    return text.format(**fmt) if fmt else text


_YES = {"yes", "y", "1", "yebo", "hongu", "ehe"}
_NO = {"no", "n", "0", "2", "kwete", "hayi", "aiwa"}


def _parse_yes_no(text: str | None) -> bool | None:
    if not text:
        return None
    t = text.strip().lower()
    if t in _YES:
        return True
    if t in _NO:
        return False
    return None


def _parse_float(text: str | None, lo: float, hi: float) -> float | None:
    if not text:
        return None
    try:
        val = float(text.strip().replace(",", "."))
    except ValueError:
        return None
    return val if lo <= val <= hi else None


def _parse_int(text: str | None, lo: int, hi: int) -> int | None:
    val = _parse_float(text, lo, hi)
    return int(val) if val is not None else None


def _parse_language(text: str | None, site_code: str | None = None) -> str | None:
    """Resolve a language choice against the site's menu.

    Accepts the menu digit, the language code, or the display label, plus a few
    name aliases — but only for languages the site actually offers, so "2" maps
    to Shona on a ZW instance and Yoruba on an NG instance.
    """
    if not text:
        return None
    t = text.strip().lower()
    menu = _menu_for_site(site_code)
    for digit, code, label in menu.options:
        if t in (digit, code, label.lower()):
            return code
    alias = _LANG_ALIASES.get(t)
    if alias is not None and any(code == alias for _, code, _ in menu.options):
        return alias
    return None


def _parse_sex(text: str | None) -> Sex | None:
    if not text:
        return None
    t = text.strip().lower()
    if t in ("1", "m", "male"):
        return Sex.MALE
    if t in ("2", "f", "female"):
        return Sex.FEMALE
    if t in ("3", "o", "other"):
        return Sex.OTHER
    return None


def _reset(session: SessionData) -> None:
    """Reset a session to first-contact state (re-used on START)."""
    session.state = ConvState.LANGUAGE
    session.language = None
    session.consent = False
    session.intake = {}
    session.audit_index = 0
    session.safety_triggers = []
    session.contextual = []


def start_session(
    phone: str, site_code: str | None = None
) -> tuple[SessionData, ConversationTurn]:
    """First contact: greet and ask for language (menu varies by site)."""
    session = SessionData(phone=phone)
    return session, ConversationTurn(replies=[_welcome(site_code)])


def advance(
    session: SessionData,
    *,
    text: str | None,
    has_video: bool,
    media_id: str | None = None,
    site_code: str | None = None,
) -> ConversationTurn:
    """Advance the conversation by one inbound message (mutates ``session``).

    ``site_code`` selects the language menu (which languages are offered and how
    digits map to them); it has no effect once a language is chosen.
    """
    lang = session.language

    # Global data-deletion command — honour the "reply STOP to delete" promise
    # from ANY state. The service erases the session row and scrubs this phone's
    # jobs; the FSM only flags intent (it cannot touch the DB).
    if text and text.strip().lower() in PURGE_COMMANDS:
        return ConversationTurn(replies=[_t("purged", lang)], purge=True)

    # A "START"/"hi" restart from a finished or declined chat begins again.
    if session.state in (ConvState.COMPLETE, ConvState.DECLINED):
        if text and text.strip().lower() in ("start", "hi", "hello", "restart"):
            _reset(session)
            return ConversationTurn(replies=[_welcome(site_code)])
        key = "complete" if session.state is ConvState.COMPLETE else "declined"
        return ConversationTurn(replies=[_t(key, lang)])

    if session.state is ConvState.LANGUAGE:
        chosen = _parse_language(text, site_code)
        if chosen is None:
            return ConversationTurn(replies=[_welcome(site_code)])
        session.language = chosen
        session.state = ConvState.CONSENT
        return ConversationTurn(replies=[_t("consent", chosen)])

    if session.state is ConvState.CONSENT:
        yn = _parse_yes_no(text)
        if yn is None:
            return ConversationTurn(replies=[_t("retry_yesno", lang, q=_t("consent", lang))])
        if not yn:
            session.state = ConvState.DECLINED
            return ConversationTurn(replies=[_t("declined", lang)])
        session.consent = True
        session.state = ConvState.AGE
        return ConversationTurn(replies=[_t("age", lang)])

    if session.state is ConvState.AGE:
        age = _parse_int(text, 1, 120)
        if age is None:
            return ConversationTurn(replies=[_t("retry_number", lang, q=_t("age", lang))])
        session.intake["age_years"] = age
        session.state = ConvState.SEX
        return ConversationTurn(replies=[_t("sex", lang)])

    if session.state is ConvState.SEX:
        sex = _parse_sex(text)
        if sex is None:
            return ConversationTurn(replies=[_t("retry_choice", lang, q=_t("sex", lang))])
        session.intake["sex"] = sex.value
        session.state = ConvState.HEIGHT
        return ConversationTurn(replies=[_t("height", lang)])

    if session.state is ConvState.HEIGHT:
        height = _parse_float(text, 50, 250)
        if height is None:
            return ConversationTurn(replies=[_t("retry_number", lang, q=_t("height", lang))])
        session.intake["height_cm"] = height
        session.state = ConvState.WEIGHT
        return ConversationTurn(replies=[_t("weight", lang)])

    if session.state is ConvState.WEIGHT:
        weight = _parse_float(text, 5, 400)
        if weight is None:
            return ConversationTurn(replies=[_t("retry_number", lang, q=_t("weight", lang))])
        session.intake["weight_kg"] = weight
        session.state = ConvState.WAIST
        return ConversationTurn(replies=[_t("waist", lang)])

    if session.state is ConvState.WAIST:
        waist = _parse_float(text, 30, 250)
        if waist is None:
            return ConversationTurn(replies=[_t("retry_number", lang, q=_t("waist", lang))])
        session.intake["waist_cm"] = waist
        session.state = ConvState.AUDIT
        session.audit_index = 0
        return ConversationTurn(replies=[AUDIT_QUESTIONS[0]["q"]])

    if session.state is ConvState.AUDIT:
        yn = _parse_yes_no(text)
        current = AUDIT_QUESTIONS[session.audit_index]
        if yn is None:
            return ConversationTurn(replies=[_t("retry_yesno", lang, q=current["q"])])
        if yn:
            if current["kind"] == "safety":
                session.safety_triggers.append(current["key"])
            else:
                session.contextual.append(current["key"])
        session.audit_index += 1
        if session.audit_index < len(AUDIT_QUESTIONS):
            return ConversationTurn(replies=[AUDIT_QUESTIONS[session.audit_index]["q"]])
        session.state = ConvState.VIDEO
        return ConversationTurn(replies=[_t("video", lang)])

    if session.state is ConvState.VIDEO:
        if has_video and media_id:
            session.state = ConvState.COMPLETE
            return ConversationTurn(
                replies=[_t("processing", lang)],
                action=EnqueueCapture(
                    media_id=media_id,
                    language=lang or "en",
                    intake=session.triage_request(),
                ),
            )
        return ConversationTurn(replies=[_t("video_expected", lang)])

    # Unreachable, but keep the contract total.
    return ConversationTurn(replies=[_t("video_expected", lang)])
