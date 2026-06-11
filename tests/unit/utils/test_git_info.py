from __future__ import annotations

from persistra.utils import git_info


def test_git_info_returns_dict():
    result = git_info()
    assert isinstance(result, dict)


def test_git_info_has_git_sha_key():
    result = git_info()
    assert "git_sha" in result


def test_git_sha_is_string():
    result = git_info()
    assert isinstance(result["git_sha"], str)


def test_git_sha_is_valid_hex_sha_or_unknown():
    sha = git_info()["git_sha"]
    assert isinstance(sha, str)
    # In a git repo the SHA is 40 hex chars; fallback is "unknown"
    assert sha == "unknown" or (len(sha) == 40 and all(c in "0123456789abcdef" for c in sha))


def test_git_info_has_expected_keys():
    result = git_info()
    assert {"git_sha", "git_dirty", "git_branch", "git_remote"} <= set(result)


def test_git_dirty_is_bool():
    result = git_info()
    assert isinstance(result["git_dirty"], bool)


def test_git_branch_is_string():
    result = git_info()
    assert isinstance(result["git_branch"], str)
