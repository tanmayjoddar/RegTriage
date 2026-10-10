"""Unit and property tests for signature normalization and clustering."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError as PydanticValidationError

from regtriage.errors import ConfigurationError
from regtriage.parsing import Failure
from regtriage.signature import (
    Cluster,
    cluster_failures,
    jaccard,
    normalize_message,
    signature_of,
)


def _failure(test: str, message: str) -> Failure:
    return Failure(test=test, message=message)


def test_hex_addresses_normalize() -> None:
    assert normalize_message("mismatch at addr 0x40001000: got 0xDEAD") == (
        "mismatch at addr <hex>: got <hex>"
    )


def test_numbers_timestamps_and_indices_normalize() -> None:
    assert normalize_message("dma len 5 at 12:34:56, lane[3]") == ("dma len <n> at <time>, lane[n]")
    assert normalize_message("timeout after 10 ns on ep 2") == "timeout after <time> on ep <n>"


def test_paths_and_verilog_literals_normalize() -> None:
    assert normalize_message("see /build/sim/test_dma.py line 64") == ("see <path> line <n>")
    assert normalize_message("data 8'hFF != 8'h00") == "data <vlit> != <vlit>"


def test_normalize_collapses_whitespace_and_case() -> None:
    assert normalize_message("  UVM_ERROR   @  t=5:\nASSERT  failed ") == (
        "uvm_error @ t=<n>: assert failed"
    )


def test_signature_is_stable_sha256() -> None:
    first = signature_of("mismatch at addr 0x40001000")
    second = signature_of("mismatch at addr 0x50002000")
    other = signature_of("clock never toggles")
    assert first == second
    assert first != other
    assert len(first) == 64


def test_jaccard_edge_cases() -> None:
    assert jaccard(set(), set()) == 1.0
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert jaccard({"a"}, {"b"}) == 0.0
    assert jaccard({"a", "b", "c"}, {"a", "b", "d"}) == pytest.approx(0.5)


def test_identical_signatures_form_one_cluster() -> None:
    failures = [
        _failure("t1", "mismatch at addr 0x40001000"),
        _failure("t2", "mismatch at addr 0x50002000"),
    ]
    (cluster,) = cluster_failures(failures)
    assert cluster.cluster_id == "cluster-001"
    assert cluster.signature == signature_of("mismatch at addr 0x1")
    assert len(cluster.members) == 2


def test_distinct_failures_stay_apart() -> None:
    failures = [_failure("t1", "mismatch at addr 0x4000"), _failure("t2", "clock stuck low")]
    clusters = cluster_failures(failures)
    assert len(clusters) == 2
    assert [c.cluster_id for c in clusters] == ["cluster-001", "cluster-002"]


def test_near_duplicates_merge_above_threshold() -> None:
    failures = [
        _failure("t1", "dma transfer length 5 mismatch on channel 0"),
        _failure("t2", "dma transfer length 9 mismatch on channel 1"),
    ]
    assert len(cluster_failures(failures, threshold=0.9)) == 1
    assert len(cluster_failures(failures, threshold=1.0)) == 1  # same token set
    far = [
        _failure("t1", "dma transfer length mismatch"),
        _failure("t2", "msi interrupt never asserted"),
    ]
    assert len(cluster_failures(far, threshold=0.75)) == 2


def test_near_duplicates_with_different_signatures_merge() -> None:
    first = "dma transfer length mismatch on channel 0"
    second = "dma transfer length mismatch on port 1"
    assert signature_of(first) != signature_of(second)
    failures = [_failure("t1", first), _failure("t2", second)]
    (merged,) = cluster_failures(failures, threshold=0.75)
    assert len(merged.members) == 2
    assert len(cluster_failures(failures, threshold=0.9)) == 2


def test_empty_input_and_bad_threshold() -> None:
    assert cluster_failures([]) == []
    with pytest.raises(ConfigurationError):
        cluster_failures([_failure("t", "x")], threshold=1.5)
    with pytest.raises(ConfigurationError):
        cluster_failures([_failure("t", "x")], threshold=-0.1)


def test_cluster_model_rejects_empty_members() -> None:
    with pytest.raises(PydanticValidationError):
        Cluster(cluster_id="cluster-001", signature="abc", members=[])


@given(st.text(max_size=200))
def test_normalize_is_idempotent(message: str) -> None:
    assert normalize_message(normalize_message(message)) == normalize_message(message)


_POOL = [
    "mismatch at addr 0x40001000",
    "mismatch at addr 0x50002000",
    "clock stuck low after reset",
    "dma transfer length 5 mismatch on channel 0",
    "dma transfer length 9 mismatch on channel 1",
    "msi interrupt never asserted",
    "",
]


def _canon(messages: list[str]) -> list[tuple[str, list[str]]]:
    failures = [_failure(f"t{i}", message) for i, message in enumerate(messages)]
    clusters = cluster_failures(failures, threshold=0.75)
    return sorted(
        (cluster.signature, sorted(f.message for f in cluster.members)) for cluster in clusters
    )


@given(st.lists(st.sampled_from(_POOL), min_size=0, max_size=10))
def test_clustering_is_order_independent(messages: list[str]) -> None:
    assert _canon(list(messages)) == _canon(list(reversed(messages)))
    assert _canon(list(messages)) == _canon(sorted(messages))


@given(st.lists(st.sampled_from(_POOL), min_size=0, max_size=10))
def test_clustering_is_idempotent(messages: list[str]) -> None:
    failures = [_failure(f"t{i}", message) for i, message in enumerate(messages)]
    first = cluster_failures(failures, threshold=0.75)
    flat = [failure for cluster in first for failure in cluster.members]
    second = cluster_failures(flat, threshold=0.75)
    assert [c.signature for c in first] == [c.signature for c in second]
    assert [sorted(f.message for f in c.members) for c in first] == [
        sorted(f.message for f in c.members) for c in second
    ]
