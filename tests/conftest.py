"""Test configuration to provide lightweight stubs when dependencies are missing."""

import sys
import types


def _ensure_stub(module_name: str, attributes: dict) -> None:
    if module_name in sys.modules:
        return
    stub = types.SimpleNamespace(**attributes)
    sys.modules[module_name] = stub


try:  # pragma: no cover - only for environments without dependencies installed
    import requests  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    _ensure_stub("requests", {"get": None})


try:  # pragma: no cover
    from dotenv import load_dotenv  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    def _noop(*_: object, **__: object) -> None:
        return None

    dotenv_stub = types.SimpleNamespace(load_dotenv=_noop)
    sys.modules["dotenv"] = dotenv_stub
    sys.modules["dotenv.load_dotenv"] = _noop
