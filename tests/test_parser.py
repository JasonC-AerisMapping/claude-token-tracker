from claude_token_tracker.core.parser import parse_session_file


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
