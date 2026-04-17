from claude_token_tracker.core.parser import parse_session_file, IncrementalScanner


def test_parse_basic_session_file(fixtures_dir):
    session = parse_session_file(fixtures_dir / "session_basic.jsonl", project="demo")
    assert session is not None
    assert session.project == "demo"
    assert session.title == "Test session title"
    assert session.model == "claude-opus-4-7"
    assert len(session.messages) == 2
    assert session.input_tokens == 180
    assert session.output_tokens == 90
    assert session.cache_create_tokens == 200
    assert session.cache_read_tokens == 1200
    assert session.total_tokens == 180 + 90 + 200 + 1200


def test_parse_returns_none_for_nonexistent_file(tmp_path):
    assert parse_session_file(tmp_path / "does-not-exist.jsonl", project="x") is None


def test_parse_skips_malformed_json_lines(tmp_path):
    f = tmp_path / "broken.jsonl"
    f.write_text(
        '{"type":"assistant","timestamp":"2026-04-15T10:00:00Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":10,"output_tokens":5}}}\n'
        'this is not json\n'
        '{"type":"assistant","timestamp":"2026-04-15T10:01:00Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":20,"output_tokens":10}}}\n'
    )
    session = parse_session_file(f, project="demo")
    assert session is not None
    assert len(session.messages) == 2
    assert session.input_tokens == 30


def test_incremental_scanner_initial_scan_parses_all(fixtures_dir, tmp_path):
    src = fixtures_dir / "session_basic.jsonl"
    root = tmp_path / "projects" / "demo"
    root.mkdir(parents=True)
    dst = root / (src.stem + ".jsonl")
    dst.write_bytes(src.read_bytes())

    scanner = IncrementalScanner(root=tmp_path / "projects")
    sessions = scanner.scan()
    assert len(sessions) == 1
    assert sessions[0].input_tokens == 180


def test_incremental_scanner_rescan_without_changes_is_noop(fixtures_dir, tmp_path):
    src = fixtures_dir / "session_basic.jsonl"
    root = tmp_path / "projects" / "demo"
    root.mkdir(parents=True)
    dst = root / (src.stem + ".jsonl")
    dst.write_bytes(src.read_bytes())

    scanner = IncrementalScanner(root=tmp_path / "projects")
    first = scanner.scan()
    second = scanner.scan()
    # Same objects returned from cache
    assert first[0] is second[0]


def test_incremental_scanner_only_reads_new_bytes(fixtures_dir, tmp_path):
    src = fixtures_dir / "session_basic.jsonl"
    root = tmp_path / "projects" / "demo"
    root.mkdir(parents=True)
    dst = root / (src.stem + ".jsonl")
    dst.write_bytes(src.read_bytes())

    scanner = IncrementalScanner(root=tmp_path / "projects")
    scanner.scan()

    # Append one more assistant message worth 5 input tokens
    with open(dst, "a", encoding="utf-8") as f:
        f.write('\n{"type":"assistant","timestamp":"2026-04-15T10:10:00Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":5,"output_tokens":3}}}\n')

    sessions = scanner.scan()
    assert len(sessions) == 1
    assert sessions[0].input_tokens == 185
    assert sessions[0].output_tokens == 93
    assert len(sessions[0].messages) == 3


def test_incremental_scanner_missing_root_returns_empty(tmp_path):
    scanner = IncrementalScanner(root=tmp_path / "does-not-exist")
    assert scanner.scan() == []


def test_incremental_scanner_removes_deleted_files(fixtures_dir, tmp_path):
    src = fixtures_dir / "session_basic.jsonl"
    root = tmp_path / "projects" / "demo"
    root.mkdir(parents=True)
    dst = root / (src.stem + ".jsonl")
    dst.write_bytes(src.read_bytes())

    scanner = IncrementalScanner(root=tmp_path / "projects")
    assert len(scanner.scan()) == 1

    dst.unlink()
    assert scanner.scan() == []
