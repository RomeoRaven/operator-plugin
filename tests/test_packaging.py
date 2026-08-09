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
    assert manifest["config"]["target_url"] == ""
    assert manifest["secrets"] == ["token"]
    assert manifest["capabilities"]["filesystem"] == "none"
    assert project["version"] == manifest["version"]


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
