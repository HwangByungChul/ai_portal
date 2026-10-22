"""Advisory, fail-closed readiness contract for dynamic tool publication.

Enforces:
- Exact-revision descriptor comparison across tool_id, revision_number, digest, and risk_policy.
- Explicit gate enablement control (fails closed by default).
- Immediate blocking on retired publications.
- Execution readiness only when active publication exists in ledger.
"""

from collections.abc import Mapping
from typing import Any

_BOUND_FIELDS = (
    "tool_id",
    "revision_number",
    "digest",
    "risk_policy_id",
    "risk_policy_revision",
)


def _valid_descriptor(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    if not isinstance(value.get("tool_id"), str) or not value["tool_id"].strip():
        return False
    revision = value.get("revision_number")
    policy_revision = value.get("risk_policy_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        return False
    if isinstance(policy_revision, bool) or not isinstance(policy_revision, int) or policy_revision < 1:
        return False
    digest = value.get("digest")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        return False
    return isinstance(value.get("risk_policy_id"), str) and bool(value["risk_policy_id"].strip())


def publication_gate(
    submitted: object,
    current: object,
    *,
    has_active_publication: bool = False,
    is_retired: bool = False,
    exact_gate_enabled: bool = False,
) -> dict[str, Any]:
    """Compare server-computed snapshots and evaluate publication authority."""
    blockers: list[str] = []

    if not exact_gate_enabled:
        blockers.append("EXACT_REVISION_APPROVAL_GATE_NOT_IMPLEMENTED")

    valid = _valid_descriptor(submitted) and _valid_descriptor(current)
    matches = bool(valid and all(submitted[field] == current[field] for field in _BOUND_FIELDS))

    if not valid:
        blockers.append("DESCRIPTOR_MISSING_OR_MALFORMED")
    elif not matches:
        blockers.append("EXACT_REVISION_SNAPSHOT_MISMATCH")
        for field, code in (
            ("tool_id", "TOOL_ID_MISMATCH"),
            ("revision_number", "REGISTRY_REVISION_MISMATCH"),
            ("digest", "REGISTRY_DIGEST_MISMATCH"),
            ("risk_policy_id", "RISK_POLICY_MISMATCH"),
            ("risk_policy_revision", "RISK_POLICY_MISMATCH"),
        ):
            if submitted[field] != current[field]:
                blockers.append(code)

    if is_retired:
        blockers.append("PUBLICATION_RETIRED")

    is_publishable = bool(
        exact_gate_enabled and valid and matches and not is_retired and len(blockers) == 0
    )
    is_execution_ready = bool(is_publishable and has_active_publication)

    return {
        "snapshot_matches": matches,
        "publishable": is_publishable,
        "execution_ready": is_execution_ready,
        "blockers": list(dict.fromkeys(blockers)),
    }
