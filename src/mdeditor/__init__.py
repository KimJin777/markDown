"""markDown 편집기."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("markdown-editor")  # 정본은 pyproject.toml의 version
except PackageNotFoundError:
    __version__ = "0.0.0"
