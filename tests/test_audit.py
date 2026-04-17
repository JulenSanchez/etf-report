import json


def test_audit_writes_to_separate_file(load_module, tmp_path):
    logger_mod = load_module("logger")
    audit_dir = tmp_path / "logs"
    audit_dir.mkdir()

    log = logger_mod.Logger(name="test_audit", file_output=True, log_dir=str(audit_dir))

    log.audit("api_call", "GET https://example.com", duration_ms=123.4, status="ok")

    audit_files = list(audit_dir.glob("audit_*.jsonl"))
    assert len(audit_files) == 1

    records = [json.loads(line) for line in audit_files[0].read_text(encoding="utf-8").strip().split("\n")]
    assert len(records) == 1
    assert records[0]["type"] == "api_call"
    assert records[0]["detail"] == "GET https://example.com"
    assert records[0]["duration_ms"] == 123.4
    assert records[0]["status"] == "ok"
    assert records[0]["level"] == "AUDIT"


def test_audit_api_call_context_manager_records_duration(load_module, tmp_path):
    logger_mod = load_module("logger")
    audit_dir = tmp_path / "logs"
    audit_dir.mkdir()

    log = logger_mod.Logger(name="test_audit_api", file_output=True, log_dir=str(audit_dir))

    with log.audit_api_call("GET", "https://example.com/api"):
        pass  # no-op

    audit_files = list(audit_dir.glob("audit_*.jsonl"))
    records = [json.loads(line) for line in audit_files[0].read_text(encoding="utf-8").strip().split("\n")]
    assert len(records) == 1
    assert records[0]["duration_ms"] >= 0
    assert records[0]["status"] == "ok"


def test_audit_api_call_context_manager_records_error_on_exception(load_module, tmp_path):
    logger_mod = load_module("logger")
    audit_dir = tmp_path / "logs"
    audit_dir.mkdir()

    log = logger_mod.Logger(name="test_audit_err", file_output=True, log_dir=str(audit_dir))

    try:
        with log.audit_api_call("GET", "https://example.com/fail"):
            raise RuntimeError("network error")
    except RuntimeError:
        pass

    audit_files = list(audit_dir.glob("audit_*.jsonl"))
    records = [json.loads(line) for line in audit_files[0].read_text(encoding="utf-8").strip().split("\n")]
    assert len(records) == 1
    assert records[0]["status"] == "error"
    assert "network error" in records[0]["extra"]["error"]


def test_audit_operation_context_manager_records_type_and_detail(load_module, tmp_path):
    logger_mod = load_module("logger")
    audit_dir = tmp_path / "logs"
    audit_dir.mkdir()

    log = logger_mod.Logger(name="test_audit_op", file_output=True, log_dir=str(audit_dir))

    with log.audit_operation("data_process", "MA calculation"):
        pass

    audit_files = list(audit_dir.glob("audit_*.jsonl"))
    records = [json.loads(line) for line in audit_files[0].read_text(encoding="utf-8").strip().split("\n")]
    assert len(records) == 1
    assert records[0]["type"] == "data_process"
    assert records[0]["detail"] == "MA calculation"


def test_audit_without_file_output_is_noop(load_module):
    logger_mod = load_module("logger")
    log = logger_mod.Logger(name="no_file", file_output=False)

    # Should not raise
    log.audit("api_call", "test")
    assert log.get_audit_file_path() is None


def test_audit_level_exists_in_levels(load_module):
    logger_mod = load_module("logger")
    assert "AUDIT" in logger_mod.Logger.LEVELS
    assert logger_mod.Logger.LEVELS["AUDIT"] > logger_mod.Logger.LEVELS["ERROR"]


def test_audit_color_exists(load_module):
    logger_mod = load_module("logger")
    assert "AUDIT" in logger_mod.Logger.COLORS
