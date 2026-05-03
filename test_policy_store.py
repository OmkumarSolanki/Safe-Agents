"""Tests for policy_store.py — validation, save/load round-trip, list, delete."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from policy_store import (
    delete_policy,
    list_policies,
    load_policy,
    save_policy,
    validate_policy,
)


REALISTIC_POLICY = """
The agent must not delete files in /home/user/Documents under any circumstance.
The agent must not send email to recipients outside the company.com domain.
The agent should ask the user before running any shell command.
The agent cannot share patient records with external parties.
""".strip()


# ---------------------------------------------------------------------------
# validate_policy
# ---------------------------------------------------------------------------

def test_validate_rejects_empty_string():
    errors = validate_policy("")
    assert errors and any("empty" in e.lower() for e in errors)


def test_validate_rejects_whitespace_only():
    errors = validate_policy("   \n\t  ")
    assert errors and any("empty" in e.lower() for e in errors)


def test_validate_rejects_too_short():
    errors = validate_policy("must not delete")
    assert errors
    assert any("too short" in e.lower() for e in errors)


def test_validate_rejects_no_rule_keywords():
    text = (
        "This is a long block of text that talks about all kinds of things "
        "but never tells the agent what to do or what to avoid doing."
    )
    errors = validate_policy(text)
    assert errors
    assert any("rule" in e.lower() or "must" in e.lower() for e in errors)


def test_validate_accepts_realistic_policy():
    assert validate_policy(REALISTIC_POLICY) == []


def test_validate_accepts_policy_with_just_should():
    text = "The agent should always confirm with the user before any destructive action that may not be reversible."
    assert validate_policy(text) == []


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------

def test_save_load_round_trip():
    with TemporaryDirectory() as td:
        d = Path(td)
        pid = save_policy(
            "My Test Policy",
            REALISTIC_POLICY,
            notes="some notes",
            policies_dir=d,
        )
        assert pid == "my-test-policy"
        loaded = load_policy(pid, policies_dir=d)
        assert loaded["policy_id"] == pid
        assert loaded["title"] == "My Test Policy"
        assert loaded["policy_text"] == REALISTIC_POLICY
        assert loaded["notes"] == "some notes"
        assert loaded["created_at"]
        assert loaded["updated_at"]
        # YAML file actually on disk under expected name
        assert (d / "my-test-policy.yaml").exists()


def test_save_invalid_policy_raises():
    with TemporaryDirectory() as td:
        d = Path(td)
        try:
            save_policy("Bad", "too short", policies_dir=d)
        except ValueError as e:
            assert "invalid policy" in str(e).lower()
        else:
            assert False, "expected ValueError"


def test_save_collision_appends_hash():
    with TemporaryDirectory() as td:
        d = Path(td)
        pid1 = save_policy("Same Title", REALISTIC_POLICY, policies_dir=d)
        pid2 = save_policy("Same Title", REALISTIC_POLICY + " extra rule.", policies_dir=d)
        assert pid1 == "same-title"
        assert pid2 != pid1
        assert pid2.startswith("same-title-")


def test_save_with_existing_id_updates_in_place():
    with TemporaryDirectory() as td:
        d = Path(td)
        pid = save_policy("Edit Me", REALISTIC_POLICY, policies_dir=d)
        first = load_policy(pid, policies_dir=d)
        new_text = REALISTIC_POLICY + "\nThe agent must not access files in /etc."
        pid2 = save_policy("Edit Me Updated", new_text, policy_id=pid, policies_dir=d)
        assert pid2 == pid
        updated = load_policy(pid, policies_dir=d)
        assert updated["title"] == "Edit Me Updated"
        assert updated["policy_text"].endswith("/etc.")
        assert updated["created_at"] == first["created_at"]
        assert updated["updated_at"] >= first["updated_at"]


# ---------------------------------------------------------------------------
# list_policies
# ---------------------------------------------------------------------------

def test_list_policies_returns_saved_entries():
    with TemporaryDirectory() as td:
        d = Path(td)
        assert list_policies(policies_dir=d) == []
        save_policy("First Policy", REALISTIC_POLICY, policies_dir=d)
        save_policy("Second Policy", REALISTIC_POLICY, policies_dir=d)
        listed = list_policies(policies_dir=d)
        titles = {p["title"] for p in listed}
        assert titles == {"First Policy", "Second Policy"}
        for entry in listed:
            assert "policy_id" in entry
            assert "updated_at" in entry


def test_list_policies_sorted_desc_by_updated_at():
    with TemporaryDirectory() as td:
        d = Path(td)
        save_policy("Older", REALISTIC_POLICY, policies_dir=d)
        # Force a slight time gap
        import time
        time.sleep(0.01)
        save_policy("Newer", REALISTIC_POLICY, policies_dir=d)
        listed = list_policies(policies_dir=d)
        assert listed[0]["title"] == "Newer"
        assert listed[1]["title"] == "Older"


# ---------------------------------------------------------------------------
# delete_policy
# ---------------------------------------------------------------------------

def test_delete_removes_the_file():
    with TemporaryDirectory() as td:
        d = Path(td)
        pid = save_policy("Doomed", REALISTIC_POLICY, policies_dir=d)
        assert (d / f"{pid}.yaml").exists()
        assert delete_policy(pid, policies_dir=d) is True
        assert not (d / f"{pid}.yaml").exists()


def test_delete_missing_returns_false():
    with TemporaryDirectory() as td:
        d = Path(td)
        assert delete_policy("does-not-exist", policies_dir=d) is False


if __name__ == "__main__":
    import sys, traceback
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError:
                failures += 1
                print(f"FAIL  {name}")
                traceback.print_exc()
            except Exception:
                failures += 1
                print(f"ERROR {name}")
                traceback.print_exc()
    sys.exit(1 if failures else 0)
