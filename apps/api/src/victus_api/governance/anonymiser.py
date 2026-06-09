"""Pure pseudonymisation helpers.

Kept in their own module so they are trivially unit-testable without
standing up a database. None of these functions touch global state — the
caller passes the salt, the caller passes the row, the caller decides
when to commit.

Rotation note: rotating ``pseudo_salt`` re-anonymises new requests but
does NOT change pseudonyms already persisted on previously-anonymised
rows. Treat the salt as a long-lived deployment secret per the
documentation on ``Settings.pseudo_salt``.
"""

from __future__ import annotations

import hashlib
import uuid

from victus_api.governance import (
    ANONYMISED_SUBJECT_PREFIX,
    TOMBSTONE_EMAIL_DOMAIN,
    TOMBSTONE_NAME,
)


def tombstone_email(user_id: uuid.UUID) -> str:
    """Return a non-routable mailto-safe tombstone for an erased user.

    The ``victus.invalid`` TLD is reserved (RFC 6761) — no real address
    can collide and any outbound mail bounces. We append the user UUID
    so two erased rows don't tie via a unique-index NULL collision when
    the index is rebuilt without the partial WHERE clause.
    """
    return f"erased+{user_id.hex}@{TOMBSTONE_EMAIL_DOMAIN}"


def tombstone_name() -> str:
    return TOMBSTONE_NAME


def pseudonymise_subject_id(
    subject_id: uuid.UUID, *, salt: str
) -> str:
    """One-way pseudonym for a study subject.

    SHA-256 over ``{subject_id.hex}:{salt}`` truncated to 12 hex chars.
    Collision space at 12 hex = 2^48, more than sufficient for per-
    researcher subject populations and short enough to remain readable
    on the study dashboard.
    """
    digest = hashlib.sha256(
        f"{subject_id.hex}:{salt}".encode()
    ).hexdigest()[:12].upper()
    return f"{ANONYMISED_SUBJECT_PREFIX}{digest}"
