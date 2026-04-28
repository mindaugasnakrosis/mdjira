"""Tests for the install-skill subcommand."""

from __future__ import annotations

from mdjira.install_skill import install_skill


def test_install_skill_copies_bundled_files(tmp_path):
    target = tmp_path / "skills" / "mdjira"
    out_path, copied = install_skill(target_dir=target, force=False)
    assert out_path == target
    assert (target / "SKILL.md").is_file()
    assert "SKILL.md" in copied


def test_install_skill_is_idempotent(tmp_path):
    target = tmp_path / "skills" / "mdjira"
    install_skill(target_dir=target, force=False)
    _, second_copied = install_skill(target_dir=target, force=False)
    # Second run: every file already matches, so nothing copied.
    assert second_copied == []


def test_install_skill_force_recopies(tmp_path):
    target = tmp_path / "skills" / "mdjira"
    install_skill(target_dir=target, force=False)
    _, copied = install_skill(target_dir=target, force=True)
    assert "SKILL.md" in copied
