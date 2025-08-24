import os, glob, json, time
from companion_ai.core.conversation_logger import log_interaction
from companion_ai.core import config

def test_conversation_logger_writes_line(tmp_path, monkeypatch):
    # Redirect LOG_DIR to temp
    monkeypatch.setenv('LOG_DIR_OVERRIDE', str(tmp_path))
    # Monkeypatch config.LOG_DIR if present
    if hasattr(config, 'LOG_DIR'):
        original = config.LOG_DIR
        config.LOG_DIR = str(tmp_path)
    try:
        log_interaction("hi", "hello", "test", "system prompt xyz", {"k":1}, model="dummy")
        time.sleep(0.05)
        files = glob.glob(os.path.join(str(tmp_path), 'conv_*.jsonl'))
        assert files, "No log file created"
        with open(files[0], 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f if l.strip()]
        assert lines, "Log file empty"
        rec = json.loads(lines[-1])
        assert rec['user'] == 'hi' and rec['ai'] == 'hello'
        assert rec['mode'] == 'test' and rec['model'] == 'dummy'
        assert 'system_prompt_hash' in rec
    finally:
        if 'original' in locals():
            config.LOG_DIR = original