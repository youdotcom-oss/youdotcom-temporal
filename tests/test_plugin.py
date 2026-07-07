from __future__ import annotations

from temporalio.plugin import SimplePlugin

from youdotcom_temporal import YouPlugin, you_activities
from youdotcom_temporal.plugin import _PASSTHROUGH_MODULES


def test_you_plugin_is_simple_plugin():
    plugin = YouPlugin()
    assert isinstance(plugin, SimplePlugin)


def test_you_plugin_name():
    plugin = YouPlugin()
    assert plugin.name() == "youdotcom.YouPlugin"


def test_passthrough_modules_include_sdk_deps():
    assert "youdotcom" in _PASSTHROUGH_MODULES
    assert "httpx" in _PASSTHROUGH_MODULES
    assert "pydantic" in _PASSTHROUGH_MODULES


def test_you_activities_matches_plugin_activities():
    acts = you_activities()
    assert len(acts) == 3
