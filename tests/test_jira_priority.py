"""Milo's priority mapping and JQL escaping — pure, deterministic, trust-relevant
(a mis-escaped string is a JQL-injection vector; a mis-matched keyword mis-triages)."""

import pytest

from subagent_config.milo._jira import _escape_jql_string, _signal_matches, map_priority


@pytest.mark.parametrize(
    "signal,expected",
    [
        (None, "Medium"),
        ("", "Medium"),
        ("urgent", "Critical"),
        ("ASAP", "Critical"),
        ("this is a blocker", "Critical"),
        ("high priority", "High"),
        ("we must do this", "High"),
        ("should probably", "Medium"),
        ("soon", "Medium"),
        ("nice to have", "Low"),
        ("optional", "Low"),
        ("low priority", "Low"),
    ],
)
def test_map_priority(signal, expected):
    assert map_priority(signal) == expected


def test_negation_forces_medium():
    assert map_priority("not urgent") == "Medium"
    assert map_priority("this isn't critical") == "Medium"
    assert map_priority("won't block the release") == "Medium"


def test_strongest_tier_wins_on_conflict():
    assert map_priority("urgent but optional") == "Critical"


def test_whole_word_match_avoids_false_positives():
    assert _signal_matches("mustard", "must") is False
    assert _signal_matches("we must ship", "must") is True
    assert map_priority("mustard tasting session") == "Medium"


def test_escape_jql_string():
    assert _escape_jql_string('a"b') == 'a\\"b'
    assert _escape_jql_string("a\\b") == "a\\\\b"
