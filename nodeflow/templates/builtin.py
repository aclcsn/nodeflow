"""Built-in node templates.

A single example template — **Sample Template** — is materialized into a project
as a YAML node spec + a one-cell notebook wired to the SDK. It declares one input
and one output of every NodeFlow port type and shows, with comments, how to read
each input type and how to produce each output type.

Public API::

    from nodeflow.templates import install_templates, template_specs
    library = install_templates(project_dir)   # writes notebooks/ + specs/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from nodeflow.core.spec import NodeSpec, ParameterSpec, ParameterType, PortSpec, dump_node_spec
from nodeflow.execution.notebook import save_notebook
from nodeflow.library import NodeLibrary


@dataclass
class TemplateDef:
    file: str
    name: str
    category: str
    code: str
    inputs: dict[str, tuple[str, bool]] = field(default_factory=dict)   # name -> (type, required)
    outputs: dict[str, str] = field(default_factory=dict)               # name -> type
    params: dict[str, dict] = field(default_factory=dict)               # name -> {type, default, choices?}
    description: str = ""


# Every NodeFlow port type. The Sample Template exposes one input and one output
# of each, so a fresh project shows how to read and produce them all.
ALL_PORT_TYPES = [
    "dataframe", "sklearn_model", "figure", "ndarray",
    "dict", "list", "text", "html", "path",
]


_SAMPLE_CODE = '''
"""Sample Template — one input and one output of every NodeFlow type.

All inputs are optional, so this node also runs on its own. Each block below
shows how to READ an input of a given type (when one is connected) and how to
PRODUCE an output of that type. The comment above each line explains the type.
"""
import matplotlib
matplotlib.use("Agg")  # render figures without a display
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from nodeflow import inputs, outputs

# ============================================================================
# READING INPUTS  (each is optional; inputs.get(name) is None when unconnected)
# ============================================================================

# dataframe: a pandas DataFrame (stored as Parquet). Use it like any DataFrame —
# select columns, filter rows, compute statistics, etc.
in_dataframe = inputs.get("in_dataframe")

# sklearn_model: a fitted scikit-learn estimator (stored via joblib). Score new
# data with in_sklearn_model.predict(X).
in_sklearn_model = inputs.get("in_sklearn_model")

# figure: the rendered image of a Matplotlib figure, returned as a NumPy RGBA
# array (it is an image, no longer an editable Figure).
in_figure = inputs.get("in_figure")

# ndarray: a NumPy array (stored as .npy). Use it for numeric or tensor data.
in_ndarray = inputs.get("in_ndarray")

# dict: a JSON-style mapping (stored as JSON). Look values up by key, e.g. a
# metrics dict or a column mapping like {"target": "y"}.
in_dict = inputs.get("in_dict")

# list: a JSON-style list of values (stored as JSON). Iterate over it.
in_list = inputs.get("in_list")

# text: a plain string (stored as .txt) — free-form notes, a SQL script, etc.
in_text = inputs.get("in_text")

# html: an HTML string (stored as .html) — a rendered report or table.
in_html = inputs.get("in_html")

# path: a filesystem path as a string. Hand it to your own loader, for example
# pd.read_csv(in_path) or db.read_csv(in_path, sep=";").
in_path = inputs.get("in_path")

# ============================================================================
# PRODUCING OUTPUTS  (assign to outputs.<name>; the port type controls storage)
# ============================================================================

# dataframe -> Parquet. Assign any pandas DataFrame.
outputs.out_dataframe = pd.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})

# sklearn_model -> joblib. Assign any fitted estimator (here a tiny classifier).
outputs.out_sklearn_model = LogisticRegression().fit([[0], [1], [2], [3]], [0, 0, 1, 1])

# figure -> PNG. Assign a Matplotlib Figure; NodeFlow saves it as an image.
_fig, _ax = plt.subplots()
_ax.plot([1, 2, 3], [3, 1, 2], marker="o")
_ax.set_title("Sample figure")
outputs.out_figure = _fig

# ndarray -> .npy. Assign a NumPy array of any shape.
outputs.out_ndarray = np.arange(12).reshape(3, 4)

# dict -> JSON. Assign a dictionary of JSON-serializable values.
outputs.out_dict = {"accuracy": 0.91, "label": "demo"}

# list -> JSON. Assign a list of JSON-serializable values.
outputs.out_list = [1, 2, 3, "four"]

# text -> .txt. Assign a string.
outputs.out_text = "This is a plain-text output from the Sample Template."

# html -> .html. Assign an HTML string; it renders in the Outputs panel.
outputs.out_html = "<h2>Sample report</h2><p>Hello from the Sample Template.</p>"

# path -> a path string. Connect this to a reader node's path input so the
# reader can open the file with its own loader.
outputs.out_path = "sample.csv"
'''.strip()


_SAMPLE_TEMPLATE = TemplateDef(
    file="sample_template",
    name="Sample Template",
    category="Examples",
    description=(
        "Example node exposing one input and one output of every NodeFlow type, "
        "with commented examples of how to read and produce each."
    ),
    inputs={f"in_{t}": (t, False) for t in ALL_PORT_TYPES},   # all optional
    outputs={f"out_{t}": t for t in ALL_PORT_TYPES},
    code=_SAMPLE_CODE,
)


TEMPLATE_DEFS: list[TemplateDef] = [_SAMPLE_TEMPLATE]


# --------------------------------------------------------------------------- #
# Build / install
# --------------------------------------------------------------------------- #
def _param_spec(cfg: dict) -> ParameterSpec:
    return ParameterSpec(
        type=ParameterType(cfg["type"]),
        default=cfg.get("default"),
        choices=cfg.get("choices"),
    )


def build_spec(t: TemplateDef) -> NodeSpec:
    return NodeSpec(
        name=t.name,
        category=t.category,
        description=t.description,
        notebook=f"notebooks/{t.file}.ipynb",
        inputs={n: PortSpec(type=ty, required=req) for n, (ty, req) in t.inputs.items()},
        outputs={n: PortSpec(type=ty) for n, ty in t.outputs.items()},
        parameters={n: _param_spec(cfg) for n, cfg in t.params.items()},
    )


def template_specs() -> list[NodeSpec]:
    return [build_spec(t) for t in TEMPLATE_DEFS]


def _params_cell(spec: NodeSpec) -> str:
    return "\n".join(f"{name} = {value!r}" for name, value in spec.default_params().items())


def install_templates(project_dir: str | Path) -> NodeLibrary:
    """Materialize all templates into ``project_dir`` and return a NodeLibrary."""
    project_dir = Path(project_dir)
    nb_dir = project_dir / "notebooks"
    specs_dir = project_dir / "specs"
    nb_dir.mkdir(parents=True, exist_ok=True)
    specs_dir.mkdir(parents=True, exist_ok=True)

    library = NodeLibrary()
    for t in TEMPLATE_DEFS:
        spec = build_spec(t)
        save_notebook([t.code], nb_dir / f"{t.file}.ipynb", parameters_cell=_params_cell(spec))
        (specs_dir / f"{t.file}.yaml").write_text(dump_node_spec(spec))
        library.add(spec)
    return library
