"""Tests for Reciprocal Rank Fusion."""

from __future__ import annotations

import pytest

from app.utils.rrf import fuse_and_order, reciprocal_rank_fusion


@pytest.mark.unit
class TestReciprocalRankFusion:
    def test_single_list_preserves_order(self):
        order = fuse_and_order([["a", "b", "c"]])
        assert order == ["a", "b", "c"]

    def test_item_in_both_lists_outranks_singletons(self):
        # "b" is high in both lists; "a" and "c" appear in only one each.
        rankings = [["a", "b", "c"], ["b", "d", "e"]]
        order = fuse_and_order(rankings)
        assert order[0] == "b"

    def test_scores_sum_across_lists(self):
        scores = reciprocal_rank_fusion([["a", "b"], ["a", "c"]], k=60)
        # "a" is rank 0 in both lists → 2 * 1/61.
        assert scores["a"] == pytest.approx(2.0 / 61)
        assert scores["b"] == pytest.approx(1.0 / 62)
        assert scores["c"] == pytest.approx(1.0 / 62)

    def test_higher_rank_scores_more(self):
        scores = reciprocal_rank_fusion([["first", "second", "third"]])
        assert scores["first"] > scores["second"] > scores["third"]

    def test_k_flattens_contribution(self):
        low_k = reciprocal_rank_fusion([["a", "b"]], k=1)
        high_k = reciprocal_rank_fusion([["a", "b"]], k=1000)
        # With larger k the gap between rank 0 and rank 1 narrows.
        assert (low_k["a"] - low_k["b"]) > (high_k["a"] - high_k["b"])

    def test_invalid_k_raises(self):
        with pytest.raises(ValueError):
            reciprocal_rank_fusion([["a"]], k=0)

    def test_deterministic_tie_break(self):
        # Two items with identical fused scores keep first-seen order.
        order = fuse_and_order([["x", "y"], ["y", "x"]])
        assert order == ["x", "y"]

    def test_empty_input(self):
        assert reciprocal_rank_fusion([]) == {}
        assert fuse_and_order([]) == []
