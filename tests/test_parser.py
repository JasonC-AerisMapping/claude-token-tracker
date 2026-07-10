from prompt_ledger.core.parser import parse_session_file, IncrementalScanner


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


def test_duplicate_message_id_lines_count_once_with_final_usage(tmp_path):
    # Real logs repeat one API call's usage on every content-block line, and
    # mid-stream lines carry a placeholder output count. Only the last line's
    # usage may be counted.
    f = tmp_path / "dup.jsonl"
    f.write_text(
        '{"type":"assistant","timestamp":"2026-04-15T10:00:00Z","message":{"id":"msg_a","model":"claude-opus-4-7","usage":{"input_tokens":2,"output_tokens":5,"cache_creation_input_tokens":300,"cache_read_input_tokens":1000}}}\n'
        '{"type":"assistant","timestamp":"2026-04-15T10:00:02Z","message":{"id":"msg_a","model":"claude-opus-4-7","usage":{"input_tokens":2,"output_tokens":5,"cache_creation_input_tokens":300,"cache_read_input_tokens":1000}}}\n'
        '{"type":"assistant","timestamp":"2026-04-15T10:00:04Z","message":{"id":"msg_a","model":"claude-opus-4-7","usage":{"input_tokens":2,"output_tokens":2101,"cache_creation_input_tokens":300,"cache_read_input_tokens":1000}}}\n'
        '{"type":"assistant","timestamp":"2026-04-15T10:01:00Z","message":{"id":"msg_b","model":"claude-opus-4-7","usage":{"input_tokens":7,"output_tokens":40,"cache_creation_input_tokens":0,"cache_read_input_tokens":1300}}}\n'
    )
    session = parse_session_file(f, project="demo")
    assert len(session.messages) == 2
    assert session.input_tokens == 2 + 7
    assert session.output_tokens == 2101 + 40  # final count, not 5 + 5 + 2101 + 40
    assert session.cache_create_tokens == 300
    assert session.cache_read_tokens == 1000 + 1300


def test_duplicate_message_id_keeps_first_timestamp(tmp_path):
    f = tmp_path / "dup_ts.jsonl"
    f.write_text(
        '{"type":"assistant","timestamp":"2026-04-15T10:00:00Z","message":{"id":"msg_a","model":"claude-opus-4-7","usage":{"input_tokens":1,"output_tokens":5}}}\n'
        '{"type":"assistant","timestamp":"2026-04-15T10:00:09Z","message":{"id":"msg_a","model":"claude-opus-4-7","usage":{"input_tokens":1,"output_tokens":90}}}\n'
    )
    session = parse_session_file(f, project="demo")
    assert len(session.messages) == 1
    assert session.messages[0].timestamp.second == 0  # anchored to when the call started
    assert session.output_tokens == 90


def test_lines_without_message_id_are_never_deduped(tmp_path):
    # The basic fixture has no ids; each id-less usage line is its own message.
    f = tmp_path / "no_ids.jsonl"
    f.write_text(
        '{"type":"assistant","timestamp":"2026-04-15T10:00:00Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":10,"output_tokens":5}}}\n'
        '{"type":"assistant","timestamp":"2026-04-15T10:01:00Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":10,"output_tokens":5}}}\n'
    )
    session = parse_session_file(f, project="demo")
    assert len(session.messages) == 2
    assert session.input_tokens == 20


def test_incremental_scan_dedupes_across_chunk_boundary(tmp_path):
    # First scan ends mid-call; the finalizing line for msg_a arrives in the
    # second scan and must update the existing message, not add a new one.
    root = tmp_path / "projects" / "demo"
    root.mkdir(parents=True)
    dst = root / "s.jsonl"
    dst.write_text(
        '{"type":"assistant","timestamp":"2026-04-15T10:00:00Z","message":{"id":"msg_a","model":"claude-opus-4-7","usage":{"input_tokens":3,"output_tokens":5,"cache_read_input_tokens":100}}}\n'
    )
    scanner = IncrementalScanner(root=tmp_path / "projects")
    first = scanner.scan()[0]
    assert first.output_tokens == 5

    with open(dst, "a", encoding="utf-8") as f:
        f.write(
            '{"type":"assistant","timestamp":"2026-04-15T10:00:03Z","message":{"id":"msg_a","model":"claude-opus-4-7","usage":{"input_tokens":3,"output_tokens":777,"cache_read_input_tokens":100}}}\n'
            '{"type":"assistant","timestamp":"2026-04-15T10:01:00Z","message":{"id":"msg_b","model":"claude-opus-4-7","usage":{"input_tokens":1,"output_tokens":2}}}\n'
        )
    second = scanner.scan()[0]
    assert len(second.messages) == 2
    assert second.output_tokens == 777 + 2
    assert second.cache_read_tokens == 100
    assert second.input_tokens == 3 + 1


def test_session_cwd_captured_from_first_entry(tmp_path):
    f = tmp_path / "cwd.jsonl"
    f.write_text(
        '{"type":"user","timestamp":"2026-04-15T10:00:00Z","cwd":"C:\\\\Users\\\\jason\\\\OneDrive\\\\Desktop\\\\Merlin"}\n'
        '{"type":"assistant","timestamp":"2026-04-15T10:00:05Z","cwd":"C:\\\\Users\\\\jason\\\\somewhere-else","message":{"id":"msg_a","model":"claude-opus-4-7","usage":{"input_tokens":1,"output_tokens":1}}}\n'
    )
    session = parse_session_file(f, project="demo")
    assert session.cwd == "C:\\Users\\jason\\OneDrive\\Desktop\\Merlin"


def test_session_cwd_none_when_absent(fixtures_dir):
    session = parse_session_file(fixtures_dir / "session_basic.jsonl", project="demo")
    assert session.cwd is None


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
