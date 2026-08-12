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
