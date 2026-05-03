"""Filesystem-backed store for user-authored business policies.

Each policy is one YAML file at ``policies/{policy_id}.yaml``.

Pure functions where possible. The only shared state is the
``policies/`` directory on disk; callers may pass in a custom
``policies_dir`` path (used by tests).
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml


DEFAULT_POLICIES_DIR = Path("policies")

MIN_POLICY_CHARS = 50
RULE_KEYWORDS = ("must not", "must", "cannot", "should not", "should")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_policy(policy_text: str) -> list[str]:
    """Return a list of validation errors. Empty list = valid policy."""
    errors: list[str] = []
    if policy_text is None or not policy_text.strip():
        errors.append("Policy text is empty.")
        return errors
    text = policy_text.strip()
    if len(text) < MIN_POLICY_CHARS:
        errors.append(
            f"Policy is too short ({len(text)} chars). Provide at least {MIN_POLICY_CHARS} characters of rules."
        )
    lower = text.lower()
    if not any(keyword in lower for keyword in RULE_KEYWORDS):
        errors.append(
            "Policy doesn't look like a rule set. Include at least one of: "
            "'must', 'must not', 'cannot', 'should', 'should not'."
        )
    return errors


# ---------------------------------------------------------------------------
# Slug + ID generation
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")
    return slug or "policy"


def _short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:6]


def _resolve_policy_id(
    title: str,
    policy_text: str,
    policies_dir: Path,
) -> str:
    base = _slugify(title)
    candidate = base
    if not (policies_dir / f"{candidate}.yaml").exists():
        return candidate
    return f"{base}-{_short_hash(policy_text + datetime.now(timezone.utc).isoformat())}"


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_policy(
    title: str,
    policy_text: str,
    notes: str = "",
    *,
    policy_id: Optional[str] = None,
    policies_dir: Path = DEFAULT_POLICIES_DIR,
) -> str:
    """Create or update a policy. Returns the policy_id.

    If ``policy_id`` is provided and exists, the file is updated in place
    (preserving ``created_at``). Otherwise a new policy is created.
    """
    if not title or not title.strip():
        raise ValueError("title is required and cannot be empty.")
    errors = validate_policy(policy_text)
    if errors:
        raise ValueError(f"Invalid policy: {'; '.join(errors)}")

    policies_dir.mkdir(parents=True, exist_ok=True)
    now = _now_iso()

    if policy_id:
        path = policies_dir / f"{policy_id}.yaml"
        if path.exists():
            existing = _load_yaml(path)
            created_at = existing.get("created_at", now)
        else:
            created_at = now
    else:
        policy_id = _resolve_policy_id(title, policy_text, policies_dir)
        path = policies_dir / f"{policy_id}.yaml"
        created_at = now

    record = {
        "policy_id": policy_id,
        "title": title.strip(),
        "created_at": created_at,
        "updated_at": now,
        "policy_text": policy_text.strip(),
        "notes": notes.strip() if notes else "",
    }
    path.write_text(
        yaml.safe_dump(record, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return policy_id


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_policy(
    policy_id: str,
    *,
    policies_dir: Path = DEFAULT_POLICIES_DIR,
) -> dict:
    path = policies_dir / f"{policy_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Policy not found: {policy_id}")
    return _load_yaml(path)


def list_policies(
    *,
    policies_dir: Path = DEFAULT_POLICIES_DIR,
) -> list[dict]:
    """Return [{policy_id, title, updated_at}, ...] sorted by updated_at desc."""
    if not policies_dir.exists():
        return []
    out: list[dict] = []
    for path in policies_dir.glob("*.yaml"):
        try:
            data = _load_yaml(path)
        except yaml.YAMLError:
            continue
        if not data:
            continue
        out.append({
            "policy_id": data.get("policy_id", path.stem),
            "title": data.get("title", path.stem),
            "updated_at": data.get("updated_at", ""),
        })
    out.sort(key=lambda p: p["updated_at"], reverse=True)
    return out


def delete_policy(
    policy_id: str,
    *,
    policies_dir: Path = DEFAULT_POLICIES_DIR,
) -> bool:
    path = policies_dir / f"{policy_id}.yaml"
    if not path.exists():
        return False
    path.unlink()
    return True
