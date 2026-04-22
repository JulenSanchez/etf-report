import os
from types import SimpleNamespace



def test_normalize_remote_url_handles_https_and_ssh(load_module):
    module = load_module("deployer")

    assert module._normalize_remote_url("https://github.com/JulenSanchez/etf-report.git") == "github.com/julensanchez/etf-report"
    assert module._normalize_remote_url("git@github.com:JulenSanchez/etf-report.git") == "github.com/julensanchez/etf-report"



def test_resolve_source_repo_root_falls_back_to_skill_dir(tmp_path, monkeypatch, load_module):
    module = load_module("deployer")
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    missing_repo = tmp_path / "missing"

    monkeypatch.setattr(
        module,
        "_is_git_repo",
        lambda path: os.path.abspath(path) == os.path.abspath(str(skill_dir)),
    )

    resolved = module._resolve_source_repo_root({"repo_root": str(missing_repo)}, str(skill_dir))

    assert resolved == str(skill_dir)



def test_detect_pages_repo_conflict_detects_same_remote_and_branch(tmp_path, monkeypatch, load_module):
    module = load_module("deployer")
    source_repo = tmp_path / "source"
    pages_repo = tmp_path / "pages"
    source_repo.mkdir()
    pages_repo.mkdir()

    monkeypatch.setattr(module, "_is_git_repo", lambda _path: True)

    def fake_get_remote(repo_root, remote_name="origin"):
        if os.path.abspath(repo_root) == os.path.abspath(str(source_repo)):
            return "https://github.com/JulenSanchez/etf-report"
        return "https://github.com/JulenSanchez/etf-report.git"

    monkeypatch.setattr(module, "_get_repo_remote_url", fake_get_remote)

    conflict = module._detect_pages_repo_conflict(
        source_repo_root=str(source_repo),
        source_branch="main",
        pages_repo_root=str(pages_repo),
        pages_branch="main",
    )

    assert conflict is not None
    assert conflict["reason"] == "same_remote_same_branch"



def test_main_skips_pages_deploy_when_pages_repo_points_to_same_remote(tmp_path, monkeypatch, load_module):
    module = load_module("deployer")
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    source_repo_root = str(skill_dir)
    deploy_calls = []

    monkeypatch.setattr(
        module,
        "get_config",
        lambda: SimpleNamespace(
            _config={
                "publish": {
                    "github": {
                        "enabled": True,
                        "repo_root": "C:/stale/path",
                        "branch": "main",
                        "pages_repo_root": "C:/pages-repo/etf-report",

                        "pages_branch": "main",
                    }
                }
            }
        ),
    )
    monkeypatch.setattr(module, "_resolve_source_repo_root", lambda config, skill_dir: source_repo_root)
    monkeypatch.setattr(
        module,
        "_deploy_to_source_repo",
        lambda config: deploy_calls.append(("source", config["repo_root"])) or True,
    )
    monkeypatch.setattr(
        module,
        "_detect_pages_repo_conflict",
        lambda **kwargs: {"reason": "same_remote_same_branch", "pages_repo_root": kwargs["pages_repo_root"]},
    )

    def fail_pages_deploy(*args, **kwargs):
        raise AssertionError("pages deploy should be skipped when it points to the same remote")

    monkeypatch.setattr(module, "_deploy_to_pages_repo", fail_pages_deploy)

    assert module.main(str(skill_dir), html_source_path=str(skill_dir / "index.html")) is True
    assert deploy_calls == [("source", source_repo_root)]
