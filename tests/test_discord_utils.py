# mypy: ignore-errors
import os
from unittest import mock

from service.discord_utils import (
    _filter_log_lines,
    _parse_log_json,
    _remove_consecutive_blank_lines,
    extract_clean_response,
    find_config,
    load_config,
    log_activity,
    query_gemini_direct,
    save_config,
)


def test_parse_log_json():
    assert _parse_log_json('{"key": "value"}') is None
    assert _parse_log_json('["list"]') == "Fallback: Invalid JSON format"
    assert _parse_log_json("invalid") is None


def test_filter_log_lines():
    lines = [
        "Normal line",
        "<thinking>",
        "Inside thinking",
        "</thinking>",
        "I will do something",
        "[System] message",
        "Another normal line",
    ]
    cleaned = _filter_log_lines(lines)
    assert cleaned == ["Normal line", "Another normal line"]


def test_remove_consecutive_blank_lines():
    lines = ["Line 1", "", "", "Line 2", "", "Line 3"]
    result = _remove_consecutive_blank_lines(lines)
    assert result == "Line 1\n\nLine 2\n\nLine 3"


def test_extract_clean_response():
    content = "Normal\n<thinking>\nthink\n</thinking>\n\nI will test\n\nResult"
    assert extract_clean_response(content) == "Normal\n\nResult"

    # Test invalid json error short circuit
    assert extract_clean_response('["list"]') == "Fallback: Invalid JSON format"


@mock.patch("service.discord_utils.os.path.exists")
@mock.patch("service.discord_utils.project_root")
def test_find_config(mock_root, mock_exists):
    mock_root.return_value = "/test/dir"
    mock_exists.side_effect = lambda p: p == "/test/dir/.agents/discord_config.json"

    assert find_config() == "/test/dir/.agents/discord_config.json"


@mock.patch.dict(os.environ, {}, clear=True)
@mock.patch("service.discord_utils.find_config")
@mock.patch(
    "builtins.open",
    new_callable=mock.mock_open,
    read_data='{"bot_token": "token", "channel_id": "chan"}',
)
def test_load_config(mock_file, mock_find):
    mock_find.return_value = "/fake.json"
    assert load_config() == {"bot_token": "token", "channel_id": "chan"}

    # Test fallback
    mock_find.return_value = None
    assert load_config() == {"bot_token": None, "channel_id": None}


@mock.patch.dict(
    os.environ,
    {"DISCORD_BOT_TOKEN": "env_token", "DISCORD_CHANNEL_ID": "env_chan"},
    clear=True,
)
def test_load_config_env_priority():
    # Env vars (.env) win over the JSON file when both are set.
    assert load_config() == {"bot_token": "env_token", "channel_id": "env_chan"}


@mock.patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "env_token"}, clear=True)
@mock.patch("service.discord_utils.find_config")
@mock.patch(
    "builtins.open",
    new_callable=mock.mock_open,
    read_data='{"bot_token": "stale_file_token", "channel_id": "file_chan"}',
)
def test_load_config_partial_env_overrides_only_that_field(mock_file, mock_find):
    # Regression test: only DISCORD_BOT_TOKEN is set in env (not
    # DISCORD_CHANNEL_ID), and a config file already has both keys. The env
    # var must still win for bot_token — an earlier version used
    # dict.setdefault(), which only fills in a key the file is missing
    # entirely, silently keeping the stale file value instead.
    mock_find.return_value = "/fake.json"
    assert load_config() == {"bot_token": "env_token", "channel_id": "file_chan"}


@mock.patch("service.discord_utils.find_config")
@mock.patch("builtins.open", new_callable=mock.mock_open)
def test_save_config(mock_file, mock_find):
    mock_find.return_value = "/fake.json"
    save_config({"key": "val"})
    mock_file.assert_called_with("/fake.json", "w", encoding="utf-8")


@mock.patch("service.discord_utils.project_root")
@mock.patch("builtins.open", new_callable=mock.mock_open)
@mock.patch("service.discord_utils.time.time")
def test_log_activity(mock_time, mock_file, mock_root):
    mock_root.return_value = "/test"
    mock_time.return_value = 1000.0
    log_activity("user", "boss", "hello")
    mock_file.assert_called_with(
        "/test/.agents/discord_activity.jsonl", "a", encoding="utf-8"
    )


@mock.patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key"})
@mock.patch("service.discord_utils.urllib.request.urlopen")
def test_query_gemini_direct(mock_urlopen):
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = (
        b'{"candidates": [{"content": {"parts": [{"text": "response text"}]}}]}'
    )
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    res = query_gemini_direct("hello", system_instruction="system")
    assert res == "response text"

    # Test error
    mock_urlopen.side_effect = Exception("HTTP Error")
    res_err = query_gemini_direct("hello")
    assert res_err is None


@mock.patch("service.discord_utils.os.path.expanduser")
@mock.patch.dict(os.environ, {}, clear=True)
def test_query_gemini_direct_no_key(mock_expanduser):
    mock_expanduser.return_value = "/does/not/exist/gemini_config.json"
    assert query_gemini_direct("hello") is None


@mock.patch("service.discord_utils.os.path.exists")
@mock.patch("service.discord_utils.os.path.expanduser")
@mock.patch(
    "builtins.open",
    new_callable=mock.mock_open,
    read_data='{"gemini_api_key": "global_key"}',
)
@mock.patch.dict(os.environ, {}, clear=True)
def test_query_gemini_direct_global_key(mock_file, mock_expanduser, mock_exists):
    mock_expanduser.return_value = "/fake/gemini_config.json"
    mock_exists.side_effect = lambda p: p == "/fake/gemini_config.json"

    with mock.patch("service.discord_utils.urllib.request.urlopen") as mock_urlopen:
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = (
            b'{"candidates": [{"content": {"parts": [{"text": "response text"}]}}]}'
        )
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = query_gemini_direct("hello")
        assert res == "response text"


@mock.patch("service.discord_utils.os.path.exists")
@mock.patch("service.discord_utils.project_root")
def test_find_config_not_found(mock_root, mock_exists):
    """Absent means absent. It used to mean "keep climbing until something
    matches", which is how a stranger's .agents/ got adopted (DT-254)."""
    mock_root.return_value = "/fake/dir"
    mock_exists.return_value = False
    assert find_config() is None


@mock.patch("service.discord_utils.find_config")
@mock.patch("builtins.open", new_callable=mock.mock_open)
@mock.patch("service.discord_utils.os.makedirs")
@mock.patch("service.discord_utils.project_root")
def test_save_config_no_config(mock_root, mock_makedirs, mock_open, mock_find):
    mock_find.return_value = None
    mock_root.return_value = "/fake/root"
    save_config({"key": "val"})
    mock_makedirs.assert_called_with("/fake/root/.agents", exist_ok=True)
    mock_open.assert_called_with(
        "/fake/root/.agents/discord_config.json", "w", encoding="utf-8"
    )


@mock.patch.dict(os.environ, {}, clear=True)
@mock.patch("service.discord_utils.find_config")
@mock.patch("builtins.open", new_callable=mock.mock_open)
def test_load_config_exception(mock_open, mock_find):
    mock_find.return_value = "/fake.json"
    mock_open.side_effect = Exception("Read error")
    assert load_config() == {"bot_token": None, "channel_id": None}


@mock.patch("service.discord_utils.project_root")
@mock.patch("builtins.open", new_callable=mock.mock_open)
def test_log_activity_exception(mock_open, mock_root):
    mock_root.return_value = "/fake"
    mock_open.side_effect = Exception("Write error")
    # Should silently pass
    log_activity("type", "author", "content")


@mock.patch("service.discord_utils.os.path.exists")
@mock.patch("service.discord_utils.os.path.expanduser")
@mock.patch("builtins.open", new_callable=mock.mock_open)
@mock.patch.dict(os.environ, {}, clear=True)
def test_query_gemini_direct_global_exception(mock_open, mock_expanduser, mock_exists):
    mock_expanduser.return_value = "/fake/gemini.json"
    mock_exists.return_value = True
    mock_open.side_effect = Exception("Json parse error")
    assert query_gemini_direct("hello") is None
