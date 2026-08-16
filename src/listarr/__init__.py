"""Listarr package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("listarr")
except PackageNotFoundError:  # pragma: no cover - source tree without install
    __version__ = "0.1.2"

__all__ = ["__version__"]
