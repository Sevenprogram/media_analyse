from datetime import date, datetime, timezone

from research.time_window import TimeWindow, filter_by_time_window, time_window_from_job, timestamp_bounds


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


def test_time_window_from_job_returns_none_when_disabled():
    job = {
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 2),
        "comment_policy": {"disable_time_window": True},
    }

    assert time_window_from_job(job) is None


def test_timestamp_bounds_returns_full_day_unix_range():
    window = TimeWindow.from_dates(date(2026, 5, 20), date(2026, 5, 22))

    start_ts, end_ts = timestamp_bounds(window)

    assert start_ts == 1779235200
    assert end_ts == 1779494399
