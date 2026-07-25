"""Deduplication / clustering tests."""

from __future__ import annotations

from gsid.ingestion.dedup import (
    cluster_items, dedup_key, detect_circular, jaccard, signature,
)


def test_signature_drops_stopwords():
    sig = signature("The attack on the port of Rotterdam")
    assert "attack" in sig and "port" in sig and "rotterdam" in sig
    assert "the" not in sig and "of" not in sig


def test_jaccard_identical():
    a = signature("port strike in rotterdam")
    assert jaccard(a, a) == 1.0


def test_cluster_groups_near_duplicates():
    texts = [
        "Ransomware disrupts port terminal operations in Busan",
        "Busan port terminal operations disrupted by ransomware attack",
        "Wildfire forces evacuations near Athens suburbs",
    ]
    clusters = cluster_items(texts, threshold=0.4)
    # first two cluster together, third separate
    sizes = sorted(len(c) for c in clusters)
    assert sizes == [1, 2]


def test_dedup_key_stable_regardless_of_word_order():
    k1 = dedup_key("Port strike halts Rotterdam operations")
    k2 = dedup_key("Rotterdam operations halts port strike")
    assert k1 == k2


def test_detect_circular():
    assert detect_circular(["Wire", "Wire", "Wire"]) is True
    assert detect_circular(["Wire", "BBC", "Reuters"]) is False
    assert detect_circular(["Wire"]) is False
