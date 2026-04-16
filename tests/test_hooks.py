"""Tests for git hook install/uninstall."""

from gemini_evolve.triggers.hook import install_hook, uninstall_hook, BEGIN_MARKER, END_MARKER


def test_install_creates_hook(tmp_path):
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    path = install_hook(tmp_path)
    assert path.exists()
    content = path.read_text()
    assert BEGIN_MARKER in content
    assert END_MARKER in content
    assert "--dry-run" not in content
    assert "evolve-all" in content


def test_install_idempotent(tmp_path):
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    install_hook(tmp_path)
    install_hook(tmp_path)
    content = (hooks / "post-commit").read_text()
    assert content.count(BEGIN_MARKER) == 1


def test_install_appends_to_existing(tmp_path):
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    hook_file = hooks / "post-commit"
    hook_file.write_text("#!/bin/bash\necho 'existing hook'\n")
    hook_file.chmod(0o755)
    install_hook(tmp_path)
    content = hook_file.read_text()
    assert "existing hook" in content
    assert BEGIN_MARKER in content


def test_uninstall_removes_cleanly(tmp_path):
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    install_hook(tmp_path)
    result = uninstall_hook(tmp_path)
    assert result is True
    # Hook file should be removed since we were the only content
    hook_file = hooks / "post-commit"
    assert not hook_file.exists()


def test_uninstall_preserves_other_content(tmp_path):
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    hook_file = hooks / "post-commit"
    hook_file.write_text("#!/bin/bash\necho 'existing hook'\n")
    hook_file.chmod(0o755)
    install_hook(tmp_path)
    uninstall_hook(tmp_path)
    content = hook_file.read_text()
    assert "existing hook" in content
    assert BEGIN_MARKER not in content
    assert END_MARKER not in content
    # Should NOT have orphan gemini-evolve code
    assert "gemini_evolve" not in content


def test_uninstall_no_hook(tmp_path):
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    assert uninstall_hook(tmp_path) is False
