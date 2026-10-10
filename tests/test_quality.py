import pandas as pd

from src.validation.quality import validate_frame


def test_quality_reports_schema_missing_range_duplicate_and_sampling_without_mutation():
    source = pd.DataFrame({
        "timestamp": pd.to_datetime(["2025-01-01T00:00:00Z", "2025-01-01T00:00:01Z",
                                     "2025-01-01T00:00:04Z", "2025-01-01T00:00:03Z"]),
        "temperature": [20.0, None, 150.0, 25.0],
    })
    before = source.copy(deep=True)
    result = validate_frame(source, required_columns=["temperature", "pressure"],
                            expected_types={"temperature": "numeric", "timestamp": "datetime"},
                            numeric_ranges={"temperature": (0, 100)},
                            timestamp_col="timestamp", expected_interval="1s")
    assert result["record_count"] == 4
    assert result["missing_counts"]["temperature"] == 1
    assert result["missing_percent"]["temperature"] == 25
    assert result["range_violations"]["temperature"] == 1
    assert result["data_types"]["temperature"] == "float64"
    assert result["type_mismatches"] == {}
    assert result["timestamp_ordering_violations"] == 1
    assert result["irregular_intervals"] >= 1
    assert not result["passed"]
    pd.testing.assert_frame_equal(source, before)


def test_empty_and_malformed_schema_is_reported():
    result = validate_frame(pd.DataFrame(), required_columns=["timestamp"], timestamp_col="timestamp")
    assert result["record_count"] == 0
    assert any("Missing required" in issue for issue in result["failures"])
    assert result["warnings"]


def test_type_mismatches_are_explicit_failures():
    result = validate_frame(pd.DataFrame({"reading": ["unknown"]}), expected_types={"reading": "numeric"})
    assert result["type_mismatches"]["reading"]["expected"] == "numeric"
    assert result["type_mismatches"]["reading"]["actual"] in {"object", "str"}
    assert not result["passed"]
