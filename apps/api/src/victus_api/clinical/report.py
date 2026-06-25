"""Clinician participant-record PDF (server-side, reportlab).

Renders a :class:`ParticipantHistory` (summary + both pathways' assessments) as a
print-ready A4 document for the clinician's records or a paper referral. Pure
``reportlab`` (manylinux wheel, no system cairo/pango) so it installs on cPanel
shared hosting. Generation is deterministic and in-memory — bytes in, bytes out
— and the caller owns access control + audit.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from victus_api.clinical.schemas import ParticipantHistory
from victus_api.db.models import User

# Brand-ish palette (mirrors the GREEN/YELLOW/RED state language used in the UI).
_INK = colors.HexColor("#0c1a24")
_MUTED = colors.HexColor("#5b6b73")
_RULE = colors.HexColor("#d7dee1")
_STATE_FILL = {
    "GREEN": colors.HexColor("#1a7f4b"),
    "YELLOW": colors.HexColor("#b7791f"),
    "RED": colors.HexColor("#c0392b"),
}


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontSize=18, textColor=_INK, spaceAfter=2
        ),
        "meta": ParagraphStyle(
            "meta", parent=base["Normal"], fontSize=8, textColor=_MUTED
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontSize=12, textColor=_INK, spaceBefore=10
        ),
        "h3": ParagraphStyle(
            "h3", parent=base["Heading3"], fontSize=10, textColor=_INK, spaceBefore=8
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], fontSize=9, textColor=_INK, leading=13
        ),
        "small": ParagraphStyle(
            "small", parent=base["Normal"], fontSize=8, textColor=_MUTED, leading=11
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["Normal"], fontSize=7, textColor=_MUTED,
            alignment=TA_CENTER,
        ),
    }


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M UTC")


def _state_chip(state: str, styles: dict[str, ParagraphStyle]) -> Table:
    """A small coloured GREEN/YELLOW/RED chip."""
    fill = _STATE_FILL.get(state, _MUTED)
    label = Paragraph(
        f'<font color="white"><b>{state}</b></font>', styles["small"]
    )
    chip = Table([[label]], colWidths=[24 * mm])
    chip.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fill),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return chip


def _summary_block(history: ParticipantHistory, styles: dict[str, ParagraphStyle]) -> Table:
    p = history.participant
    rows = [
        ["Name", p.full_name or "—", "Site", p.site_code],
        ["Email", p.email or "—", "Role", p.role],
        [
            "Status",
            "Active" if p.is_active else "Inactive",
            "Last activity",
            _fmt_dt(p.last_activity),
        ],
        ["Triage records", str(p.triage_count), "TOI records", str(p.toi_count)],
    ]
    table = Table(rows, colWidths=[26 * mm, 62 * mm, 26 * mm, 56 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("TEXTCOLOR", (0, 0), (0, -1), _MUTED),
                ("TEXTCOLOR", (2, 0), (2, -1), _MUTED),
                ("TEXTCOLOR", (1, 0), (1, -1), _INK),
                ("TEXTCOLOR", (3, 0), (3, -1), _INK),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, _RULE),
            ]
        )
    )
    return table


def _triage_section(history: ParticipantHistory, styles: dict[str, ParagraphStyle]) -> list:
    flow: list = [Paragraph("Pathway A — 3B-Triage", styles["h2"])]
    if not history.triage:
        flow.append(Paragraph("No triage assessments recorded.", styles["small"]))
        return flow
    for t in history.triage:
        header = Table(
            [
                [
                    Paragraph(_fmt_dt(t.created_at), styles["body"]),
                    _state_chip(t.overall_state.value, styles),
                ]
            ],
            colWidths=[120 * mm, 50 * mm],
        )
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        flow.append(header)

        disease_rows = [["Disease", "State", "Top class", "Next action"]]
        for d in t.per_disease:
            disease_rows.append(
                [d.disease.value, d.state.value, d.top_class.value, d.next_action]
            )
        dt = Table(disease_rows, colWidths=[34 * mm, 22 * mm, 34 * mm, 80 * mm])
        dt.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
                    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
                    ("TEXTCOLOR", (0, 0), (-1, 0), _MUTED),
                    ("TEXTCOLOR", (0, 1), (-1, -1), _INK),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.4, _RULE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        flow.append(Spacer(1, 2))
        flow.append(dt)
        if t.safety_override_triggered:
            flow.append(
                Paragraph(
                    "<b>Safety override:</b> " + ", ".join(t.override_reasons or ["triggered"]),
                    styles["small"],
                )
            )
        flow.append(Spacer(1, 6))
    return flow


def _toi_section(history: ParticipantHistory, styles: dict[str, ParagraphStyle]) -> list:
    flow: list = [Paragraph("Pathway B — TOI biomarkers", styles["h2"])]
    if not history.toi:
        flow.append(Paragraph("No TOI assessments recorded.", styles["small"]))
        return flow
    for a in history.toi:
        flow.append(
            Paragraph(
                f"{_fmt_dt(a.created_at)} &nbsp;·&nbsp; quality <b>{a.quality.value}</b>",
                styles["body"],
            )
        )
        rows = [["Biomarker", "Value", "Unit"]]
        for name, bm in a.biomarkers.items():
            rows.append(
                [
                    name.replace("_", " "),
                    f"{bm.value:.1f}" + ("*" if bm.experimental else ""),
                    bm.unit,
                ]
            )
        bt = Table(rows, colWidths=[60 * mm, 30 * mm, 30 * mm])
        bt.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
                    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
                    ("TEXTCOLOR", (0, 0), (-1, 0), _MUTED),
                    ("TEXTCOLOR", (0, 1), (-1, -1), _INK),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.4, _RULE),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        flow.append(Spacer(1, 2))
        flow.append(bt)
        if a.warnings:
            flow.append(Paragraph("Notes: " + "; ".join(a.warnings), styles["small"]))
        flow.append(Spacer(1, 6))
    return flow


_DISCLAIMER = (
    "Victus AI is a decision-support screening tool, not a diagnostic device. "
    "Triage states (GREEN/YELLOW/RED) and TOI biomarkers (* = experimental) are "
    "estimates with uncertainty and must be interpreted by a qualified clinician "
    "alongside the full clinical picture. Confidential — contains protected health "
    "information."
)


def _footer(canvas, doc) -> None:  # noqa: ANN001 - reportlab callback signature
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(_MUTED)
    canvas.drawCentredString(
        A4[0] / 2, 12 * mm, f"Victus AI — confidential clinical record · page {doc.page}"
    )
    canvas.restoreState()


def build_participant_report_pdf(
    history: ParticipantHistory,
    *,
    generated_by: User,
    generated_at: datetime,
) -> bytes:
    """Render the participant record to PDF bytes."""
    styles = _styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title="Victus AI — participant record",
        author="Victus AI",
    )

    actor = generated_by.full_name or generated_by.email or "Clinician"
    flow: list = [
        Paragraph("Participant clinical record", styles["title"]),
        Paragraph(
            f"Generated by {actor} ({generated_by.role.value}) · {_fmt_dt(generated_at)}",
            styles["meta"],
        ),
        Spacer(1, 4),
        HRFlowable(width="100%", thickness=0.6, color=_RULE),
        Spacer(1, 6),
        _summary_block(history, styles),
        *_triage_section(history, styles),
        *_toi_section(history, styles),
        Spacer(1, 10),
        HRFlowable(width="100%", thickness=0.4, color=_RULE),
        Spacer(1, 4),
        Paragraph(_DISCLAIMER, styles["small"]),
    ]

    doc.build(flow, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
