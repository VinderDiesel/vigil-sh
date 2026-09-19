"""Content addressing for Vigil artifacts.

Three distinct identifiers, three distinct jobs:

    raw_hash        "these are the bytes we ingested"      -> audit
    canonical_hash  "these are the bytes after we cleaned"  -> identity/cache
    cluster_id      "these look semantically related"       -> advisory only

Mixing them up is the most common way to build an eval system that silently
deletes its rarest failures. Do not.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

CAS_PREFIX = "cas"


def canonical_bytes(obj: Any) -> bytes:
    """Deterministic serialization.

    - sort_keys: field order is not meaning
    - separators: no incidental whitespace
    - ensure_ascii: stable across locales
    - allow_nan=False: NaN/Infinity are not valid JSON and break reproducibility
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_digest(obj: Any) -> str:
    return digest_bytes(canonical_bytes(obj))


def cas_uri(obj: Any) -> str:
    """cas://sha256/<hex> -- stable, printable, greppable in issues."""
    return f"{CAS_PREFIX}://sha256/{canonical_digest(obj)}"


def raw_digest(data: bytes) -> str:
    return digest_bytes(data)


def short_id(digest: str, length: int = 12) -> str:
    return digest[:length]
