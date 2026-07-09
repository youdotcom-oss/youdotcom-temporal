from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

__version__: str
try:
    __version__ = _pkg_version("youdotcom-temporal")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

from .activities import (
    set_config,
    you_activities,
    youdotcom_contents,
    youdotcom_research,
    youdotcom_search,
)
from .config import YouConfig
from .models import ContentsInput, ResearchInput, SearchInput
from .plugin import YouPlugin

__all__ = [
    "youdotcom_search",
    "youdotcom_research",
    "youdotcom_contents",
    "you_activities",
    "set_config",
    "YouPlugin",
    "YouConfig",
    "SearchInput",
    "ResearchInput",
    "ContentsInput",
    "__version__",
]
