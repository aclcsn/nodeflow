"""Built-in serializers for NodeFlow's standard types.

    dataframe      -> parquet     (pandas + pyarrow)
    sklearn_model  -> joblib
    figure         -> png         (matplotlib)
    dict / list    -> json
    ndarray        -> npy         (numpy)
    html           -> html
    text           -> txt

Two performance rules keep this module cheap to import and cheap to use:

1. **Lazy heavy imports.** pandas / numpy / joblib / matplotlib are imported
   *inside* the (de)serialize functions, never at module scope.
2. **Import-free detectors.** Auto-detection runs on every undeclared output, so
   detectors identify objects by class module/name (MRO walk) rather than by
   importing the owning library.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .registry import registry


# --------------------------------------------------------------------------- #
# Import-free detectors
# --------------------------------------------------------------------------- #
def _class_chain(obj: Any):
    return type(obj).__mro__


def _is_dataframe(obj: Any) -> bool:
    return any(
        c.__name__ == "DataFrame" and c.__module__.startswith("pandas")
        for c in _class_chain(obj)
    )


def _is_ndarray(obj: Any) -> bool:
    return any(
        c.__name__ == "ndarray" and c.__module__.startswith("numpy")
        for c in _class_chain(obj)
    )


def _is_figure(obj: Any) -> bool:
    return any(
        c.__name__ == "Figure" and c.__module__.startswith("matplotlib")
        for c in _class_chain(obj)
    )


def _is_sklearn_model(obj: Any) -> bool:
    # Any class in the MRO defined under the sklearn package, *and* a fittable
    # estimator (has fit) so we don't grab unrelated sklearn helper objects.
    in_sklearn = any(c.__module__.split(".")[0] == "sklearn" for c in _class_chain(obj))
    return in_sklearn and hasattr(obj, "fit")


# --------------------------------------------------------------------------- #
# JSON helpers (robust to numpy / pandas scalars)
# --------------------------------------------------------------------------- #
def _json_default(value: Any) -> Any:
    # numpy scalar / array
    if hasattr(value, "item") and not isinstance(value, type):
        try:
            return value.item()
        except Exception:
            pass
    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


# --------------------------------------------------------------------------- #
# dataframe -> parquet
# --------------------------------------------------------------------------- #
def _df_serialize(obj: Any, path: Path) -> dict:
    obj.to_parquet(path)  # engine: pyarrow
    return {
        "shape": list(obj.shape),
        "columns": [str(c) for c in obj.columns],
        "dtypes": {str(c): str(t) for c, t in obj.dtypes.items()},
    }


def _df_deserialize(path: Path) -> Any:
    import pandas as pd

    return pd.read_parquet(path)


# --------------------------------------------------------------------------- #
# sklearn_model -> joblib
# --------------------------------------------------------------------------- #
def _model_serialize(obj: Any, path: Path) -> dict:
    import joblib

    joblib.dump(obj, path)
    meta = {"class": type(obj).__name__, "module": type(obj).__module__}
    get_params = getattr(obj, "get_params", None)
    if callable(get_params):
        try:
            meta["params"] = {k: _json_default(v) for k, v in get_params().items()}
        except Exception:
            pass
    return meta


def _model_deserialize(path: Path) -> Any:
    import joblib

    return joblib.load(path)


# --------------------------------------------------------------------------- #
# figure -> png
# --------------------------------------------------------------------------- #
def _figure_serialize(obj: Any, path: Path) -> dict:
    obj.savefig(path, dpi=getattr(obj, "dpi", 100) or 100, bbox_inches="tight")
    try:
        w, h = obj.get_size_inches()
        return {"width_in": float(w), "height_in": float(h), "dpi": float(obj.dpi)}
    except Exception:
        return {}


def _figure_deserialize(path: Path) -> Any:
    import matplotlib.image as mpimg

    return mpimg.imread(path)


# --------------------------------------------------------------------------- #
# dict / list -> json
# --------------------------------------------------------------------------- #
def _json_serialize(obj: Any, path: Path) -> dict:
    text = json.dumps(obj, indent=2, default=_json_default)
    path.write_text(text)
    meta: dict[str, Any] = {"bytes": len(text)}
    if isinstance(obj, (dict, list)):
        meta["length"] = len(obj)
    return meta


def _json_deserialize(path: Path) -> Any:
    return json.loads(path.read_text())


# --------------------------------------------------------------------------- #
# ndarray -> npy
# --------------------------------------------------------------------------- #
def _ndarray_serialize(obj: Any, path: Path) -> dict:
    import numpy as np

    # path already ends in .npy, so np.save will not append a second suffix.
    np.save(path, obj, allow_pickle=False)
    return {"shape": list(obj.shape), "dtype": str(obj.dtype)}


def _ndarray_deserialize(path: Path) -> Any:
    import numpy as np

    return np.load(path, allow_pickle=False)


# --------------------------------------------------------------------------- #
# html / text -> html / txt
# --------------------------------------------------------------------------- #
def _html_serialize(obj: Any, path: Path) -> dict:
    if isinstance(obj, str):
        html = obj
    else:
        repr_html = getattr(obj, "_repr_html_", None)
        html = repr_html() if callable(repr_html) else str(obj)
    path.write_text(html)
    return {"bytes": len(html)}


def _text_serialize(obj: Any, path: Path) -> dict:
    text = obj if isinstance(obj, str) else str(obj)
    path.write_text(text)
    return {"bytes": len(text)}


def _read_text(path: Path) -> str:
    return path.read_text()


# --------------------------------------------------------------------------- #
# Registration (idempotent)
# --------------------------------------------------------------------------- #
_BUILTINS = [
    # name, serialize, deserialize, ext, detector, description
    ("dataframe", _df_serialize, _df_deserialize, "parquet", _is_dataframe, "pandas DataFrame as Parquet"),
    ("sklearn_model", _model_serialize, _model_deserialize, "joblib", _is_sklearn_model, "scikit-learn estimator via joblib"),
    ("figure", _figure_serialize, _figure_deserialize, "png", _is_figure, "matplotlib Figure as PNG"),
    ("ndarray", _ndarray_serialize, _ndarray_deserialize, "npy", _is_ndarray, "NumPy array as .npy"),
    ("dict", _json_serialize, _json_deserialize, "json", lambda o: isinstance(o, dict), "dict as JSON"),
    ("list", _json_serialize, _json_deserialize, "json", lambda o: isinstance(o, list), "list as JSON"),
    ("text", _text_serialize, _read_text, "txt", lambda o: isinstance(o, str), "text as .txt"),
    ("html", _html_serialize, _read_text, "html", None, "HTML as .html (declared explicitly)"),
    ("path", _text_serialize, _read_text, "txt", None, "filesystem path as text (declared explicitly)"),
]


def register_builtins(target=registry) -> None:
    """Register all built-in serializers on ``target`` (idempotent)."""
    for name, ser, deser, ext, det, desc in _BUILTINS:
        if not target.has(name):
            target.register(name, ser, deser, ext, detector=det, description=desc)


register_builtins()
