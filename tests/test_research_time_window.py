from datetime import date, datetime, timezone

from research.time_window import TimeWindow, filter_by_time_window


def test_time_window_contains_full_end_date():
    window = TimeWindow.from_dates(date(2026, 1, 1), date(2026, 1, 2))

    assert window.contains(datetime(2026, 1, 2, 23, 59, tzinfo=timezone.utc))


def test_filter_by_time_window_counts_outside_and_missing():
    window = TimeWindow.from_dates(date(2026, 1, 1), date(2026, 1, 1))
    records = [
        {"publish_time": datetime(2026, 1, 1, 12, tzinfo=timezone.utc)},
        {"publish_time": datetime(2026, 1, 2, 12, tzinfo=timezone.utc)},
        {"publish_time": None},
    ]

    accepted, outside, missing = filter_by_time_window(records, window=window)

    assert accepted == [records[0]]
    assert outside == 1
    assert missing == 1
