from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_archive_tokens_are_present():
    """아카이브와 같은 토큰을 쓴다. 값이 바뀌면 화면 색이 통째로 어긋난다."""
    css = (ROOT / "app/core/tokens.css").read_text(encoding="utf-8")
    for token in ["--bg: #eef0f3", "--accent: #23508f", "--up: #c73e3a", "--down: #2f6bd0"]:
        assert token in css, f"{token} 이 tokens.css 에 없다"


def test_app_shell_is_480px():
    css = (ROOT / "app/core/base.css").read_text(encoding="utf-8")
    assert "max-width: 480px" in css
