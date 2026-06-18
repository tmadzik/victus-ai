"""Localized WhatsApp chat copy for capture outcomes.

Three languages from the business plan (§3.2): English, Shona (sn), Ndebele (nd).

IMPORTANT: the Shona and Ndebele strings are first-pass and MUST be reviewed by
a native clinical translator before any real participant contact — medical
wording carries consent and safety weight. English is authoritative for now.

The processor stays language-agnostic: it picks a template by ``lang`` and fills
vitals. Adding a language = adding a dict entry; no code changes.
"""

from __future__ import annotations

DEFAULT_LANG = "en"
SUPPORTED_LANGS = ("en", "sn", "nd")

# Each language provides: result (vitals summary), rejected (re-record), error.
_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "result": (
            "✅ Your Victus check-up is ready.\n\n"
            "❤️ Heart rate: {hr} bpm\n"
            "🫁 Breathing rate: {rr} breaths/min\n"
            "📈 Heart-rate variability: {hrv}\n\n"
            "This is a wellness screening, *not a medical diagnosis*. "
            "Please share these results with a clinician. "
            "If you feel unwell, seek care now."
        ),
        "rejected": (
            "We couldn't read a clear signal from that video. "
            "Please re-record a 30-second clip: face a window or bright light, "
            "hold the phone steady, and keep your whole face in view."
        ),
        "error": (
            "Something went wrong processing your video. "
            "Please try sending it again in a few minutes."
        ),
    },
    "sn": {
        "result": (
            "✅ Ongororo yenyu yeVictus yagadzirira.\n\n"
            "❤️ Kurova kwemwoyo: {hr} bpm\n"
            "🫁 Kufema: {rr} paminiti\n"
            "📈 Kusiyana kwekurova kwemwoyo: {hrv}\n\n"
            "Iyi iongororo yehutano, *haisi chiremba*. "
            "Ratidzai zvabuda kuna chiremba. Kana musinganzwi zvakanaka, "
            "tsvagai rubatsiro izvozvi."
        ),
        "rejected": (
            "Hatina kukwanisa kuverenga vhidhiyo iyi zvakajeka. "
            "Tapota dzokororai mutore vhidhiyo yemasekonzi makumi matatu: "
            "tarisanai nechiedza, batai foni yakatsiga, uso hwese huoneke."
        ),
        "error": (
            "Pane chakanganisika pakugadzirisa vhidhiyo yenyu. "
            "Tapota edzai kutumirazve mushure memaminiti mashoma."
        ),
    },
    "nd": {
        "result": (
            "✅ Ukuhlolwa kwakho kweVictus sekulungile.\n\n"
            "❤️ Ukutshaya kwenhliziyo: {hr} bpm\n"
            "🫁 Ukuphefumula: {rr} ngomzuzu\n"
            "📈 Ukwehluka kokutshaya kwenhliziyo: {hrv}\n\n"
            "Lokhu kuhlolwa kwempilo, *hatshi ukuxilongwa*. "
            "Ngicela wabelane lalokhu ledokotela. Nxa ungazizwa kuhle, "
            "dinga usizo khathesi."
        ),
        "rejected": (
            "Asikwazanga ukubala ividiyo leyo kuhle. "
            "Ngicela uphinde uthathe ividiyo yemizuzwana engamatshumi amathathu: "
            "khangela ekukhanyeni, ubambe ifoni iqine, ubuso bonke bubonakale."
        ),
        "error": (
            "Kukhona okungahambanga kuhle ekulungiseni ividiyo yakho. "
            "Ngicela uzame ukuyithumela futhi emizuzwini embalwa."
        ),
    },
}


def _lang(lang: str | None) -> str:
    return lang if lang in _MESSAGES else DEFAULT_LANG


def result_message(lang: str | None, *, hr: str, rr: str, hrv: str) -> str:
    """Vitals summary for a successful check-up."""
    return _MESSAGES[_lang(lang)]["result"].format(hr=hr, rr=rr, hrv=hrv)


def rejected_message(lang: str | None) -> str:
    """Ask the user to re-record (capture unusable — a normal outcome)."""
    return _MESSAGES[_lang(lang)]["rejected"]


def error_message(lang: str | None) -> str:
    """Generic processing failure shown after retries are exhausted."""
    return _MESSAGES[_lang(lang)]["error"]
