"""Durable You.com Activities for Temporal.

Public names resolve lazily (:pep:`562`). Importing this package must not pull
in the You.com SDK: the workflow sandbox rejects the SDK's ``urllib.request``
use, and Python imports this package before any submodule's
``workflow.unsafe.imports_passed_through()`` block can run. Eager imports here
would therefore make *every* ``youdotcom_temporal.*`` import unusable from a
Workflow file, including the models a Nexus caller needs.

``from youdotcom_temporal import YouPlugin`` and friends work exactly as
before; the underlying module is imported on first attribute access.
"""

from importlib import import_module
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import TYPE_CHECKING, Any

__version__: str
try:
    __version__ = _pkg_version("youdotcom-temporal")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

if TYPE_CHECKING:
    from .activities import (
        set_config,
        you_activities,
        youdotcom_answer,
        youdotcom_contents,
        youdotcom_finance_research,
        youdotcom_research,
        youdotcom_research_background,
        youdotcom_search,
    )
    from .config import YouConfig
    from .models import (
        AnswerInput,
        ContentsInput,
        FinanceResearchInput,
        ResearchInput,
        SearchInput,
    )
    from .plugin import YouPlugin

# Public name -> submodule that defines it.
_LAZY_NAMES = {
    "set_config": "activities",
    "you_activities": "activities",
    "youdotcom_answer": "activities",
    "youdotcom_contents": "activities",
    "youdotcom_finance_research": "activities",
    "youdotcom_research": "activities",
    "youdotcom_research_background": "activities",
    "youdotcom_search": "activities",
    "YouConfig": "config",
    "AnswerInput": "models",
    "ContentsInput": "models",
    "FinanceResearchInput": "models",
    "ResearchInput": "models",
    "SearchInput": "models",
    "YouPlugin": "plugin",
}


def __getattr__(name: str) -> Any:
    module = _LAZY_NAMES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module}", __name__), name)
    globals()[name] = value  # cache so __getattr__ runs once per name
    return value


def __dir__() -> list[str]:
    return sorted(__all__)


__all__ = [
    "youdotcom_search",
    "youdotcom_research",
    "youdotcom_research_background",
    "youdotcom_contents",
    "youdotcom_answer",
    "youdotcom_finance_research",
    "you_activities",
    "set_config",
    "YouPlugin",
    "YouConfig",
    "SearchInput",
    "ResearchInput",
    "ContentsInput",
    "AnswerInput",
    "FinanceResearchInput",
    "__version__",
]
