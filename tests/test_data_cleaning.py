def test_normalize_corporate_action_events_accepts_legacy_split_shape(load_module):
    module = load_module("data_cleaning")

    normalized = module.normalize_corporate_action_events([
        {"ex_date": "2026-02-03", "ratio": 3, "note": "legacy split event"}
    ])

    assert normalized == [
        {
            "ex_date": "2026-02-03",
            "ratio": 3.0,
            "note": "legacy split event",
            "action": "share_split",
        }
    ]


def test_run_data_cleaning_pipeline_rebases_pre_event_prices_and_volume(load_module):
    module = load_module("data_cleaning")
    data = {
        "dates": ["2026-02-02", "2026-02-03", "2026-02-04"],
        "kline": [
            [3.287, 3.16, 3.15, 3.344],
            [1.074, 1.084, 1.046, 1.095],
            [1.061, 1.051, 1.029, 1.075],
        ],
        "volumes": [100, 200, 300],
        "latest_close": 1.051,
        "latest_change": -3.04,
    }

    cleaned = module.run_data_cleaning_pipeline(data, [
        {"action": "share_split", "ex_date": "2026-02-03", "ratio": 3.0}
    ])

    assert cleaned["kline"][0] == [1.096, 1.053, 1.05, 1.115]
    assert cleaned["kline"][1] == [1.074, 1.084, 1.046, 1.095]
    assert cleaned["volumes"] == [300, 200, 300]
    assert cleaned["latest_change"] == -3.04


def test_apply_share_change_events_supports_multiple_events(load_module):
    module = load_module("data_cleaning")
    data = {
        "dates": ["2026-01-10", "2026-02-10", "2026-03-02"],
        "kline": [
            [12.0, 12.0, 11.0, 13.0],
            [4.0, 4.0, 3.6, 4.4],
            [2.0, 2.1, 1.9, 2.2],
        ],
        "volumes": [10, 20, 30],
        "latest_close": 2.1,
        "latest_change": 5.0,
    }

    cleaned = module.apply_share_change_events(data, [
        {"action": "share_split", "ex_date": "2026-02-03", "ratio": 3.0},
        {"action": "share_change", "ex_date": "2026-03-01", "ratio": 2.0},
    ])

    assert cleaned["kline"][0] == [2.0, 2.0, 1.833, 2.167]
    assert cleaned["kline"][1] == [2.0, 2.0, 1.8, 2.2]
    assert cleaned["kline"][2] == [2.0, 2.1, 1.9, 2.2]
    assert cleaned["volumes"] == [60, 40, 30]



def test_apply_share_change_events_shifts_boundary_to_cover_last_pre_event_day(load_module):
    module = load_module("data_cleaning")
    data = {
        "dates": ["2026-02-02", "2026-02-03", "2026-02-04"],
        "kline": [
            [3.287, 3.16, 3.15, 3.344],
            [1.074, 1.084, 1.046, 1.095],
            [1.061, 1.051, 1.029, 1.075],
        ],
        "volumes": [100, 200, 300],
        "latest_close": 1.051,
        "latest_change": -3.04,
    }

    cleaned = module.apply_share_change_events(data, [
        {"action": "share_split", "ex_date": "2026-02-02", "ratio": 3.0, "source": "detected"}
    ])

    assert cleaned["kline"][0] == [1.096, 1.053, 1.05, 1.115]
    assert cleaned["kline"][1] == [1.074, 1.084, 1.046, 1.095]
    assert cleaned["volumes"] == [300, 200, 300]


