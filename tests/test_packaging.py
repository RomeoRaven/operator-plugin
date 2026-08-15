from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def test_manifest_and_project_are_safe_and_version_locked():
    manifest = yaml.safe_load((ROOT / "protoagent.plugin.yaml").read_text())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

    assert manifest["id"] == "operator_control"
    assert manifest["enabled"] is False
    assert manifest["min_protoagent_version"] == "0.131.3"
    assert manifest["config"]["targets"] == []
    assert manifest["config"]["target_tokens"] == ""
    assert manifest["secrets"] == ["target_tokens"]
    assert manifest["capabilities"]["filesystem"] == "none"
    assert manifest["repository"] == "https://github.com/RomeoRaven/operator-plugin"
    assert manifest["homepage"] == "https://agent.protolabs.studio"
    assert manifest["requires_pip"] == [{"pkg": "httpx>=0.27,<1", "scope": "host"}]
    settings = {field["key"]: field for field in manifest["settings"]}
    assert settings["targets"]["type"] == "string_list"
    assert settings["target_tokens"]["type"] == "secret"
    assert settings["timeout_seconds"]["type"] == "number"
    assert project["version"] == manifest["version"] == "0.5.0"
    license_text = (ROOT / "LICENSE").read_text()
    assert license_text.startswith("MIT License\n")
    assert "Copyright (c) 2026 RomeoRaven" in license_text

    readme = (ROOT / "README.md").read_text()
    proto = (ROOT / "PROTO.md").read_text()
    normalized_readme = " ".join(readme.split())
    assert "| Linux |" in readme
    assert "| Windows |" in readme
    assert "| macOS |" in readme
    assert "CI coverage (not current-head proof)" in readme
    assert "pull requests and pushes to main" in normalized_readme
    assert "every pushed/PR head" not in normalized_readme
    assert "0.136.0" in readme
    assert "1d80d15e229ac51a419b53c3378db1bea4796379" in readme
    assert "qualification host candidate" in normalized_readme
    assert "0.136.0" in proto
    assert "1d80d15e229ac51a419b53c3378db1bea4796379" in proto
    assert "campaign baseline, not installed-runtime acceptance" in " ".join(proto.split())
    assert "Current exact-head installed-runtime acceptance: **Not tested**" in readme
    assert "PC1 install/load/lifecycle acceptance is **Not tested**" in normalized_readme
    assert "not PC1 acceptance" in normalized_readme
    for contradictory_claim in (
        "is installed-runtime acceptance",
        "acceptance is tested and accepted",
        "acceptance is tested and passed",
        "acceptance has passed",
        "CI proves current-head",
        "current-head CI passed",
    ):
        assert contradictory_claim not in normalized_readme


def test_ci_covers_declared_platforms():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    for runner in ("ubuntu-latest", "windows-latest", "macos-latest"):
        assert runner in workflow
    assert "pytest -q" in workflow
    assert "ruff check ." in workflow
    assert "ruff format --check ." in workflow


def test_entry_imports_with_protoagent_host_package_semantics(monkeypatch):
    """The host loads a plugin as a package; sibling imports must be relative."""
    module_name = "protoagent_plugin_operator_control_contract_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    assert spec is not None and spec.loader is not None

    monkeypatch.setattr(
        sys,
        "path",
        [entry for entry in sys.path if entry not in {"", str(ROOT)}],
    )
    monkeypatch.delitem(sys.modules, "snapshot", raising=False)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)

    spec.loader.exec_module(module)

    assert callable(module.register)
