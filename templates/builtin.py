"""Built-in node templates.

Each template is materialized into a project as a YAML node spec + a one-cell
notebook wired to the SDK. Notebooks degrade gracefully when an optional library
is missing (XGBoost → sklearn GradientBoosting; SHAP → feature importances) so a
freshly installed project always executes end-to-end.

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


# --------------------------------------------------------------------------- #
# Template definitions
# --------------------------------------------------------------------------- #
_IMPORT_CSV = TemplateDef(
    file="import_csv",
    name="Import CSV",
    category="Input",
    description="Load a CSV by path, or synthesize a sample classification dataset.",
    outputs={"raw": "dataframe"},
    params={
        "path": {"type": "str", "default": ""},
        "n_samples": {"type": "int", "default": 300},
        "n_features": {"type": "int", "default": 6},
    },
    code="""
import pandas as pd
from nodeflow import outputs, params

path = params.get("path", "")
if path:
    df = pd.read_csv(path)
else:
    from sklearn.datasets import make_classification
    X, y = make_classification(
        n_samples=int(params.get("n_samples", 300)),
        n_features=int(params.get("n_features", 6)),
        n_informative=4, random_state=0,
    )
    df = pd.DataFrame(X, columns=[f"f{i}" for i in range(X.shape[1])])
    df["target"] = y
outputs.raw = df
""".strip(),
)

_SQL_QUERY = TemplateDef(
    file="sql_query",
    name="SQL Query",
    category="Input",
    description="Run a SQL query against a SQLite database, or synthesize sample rows.",
    outputs={"result": "dataframe"},
    params={
        "connection": {"type": "str", "default": ""},
        "query": {"type": "str", "default": ""},
    },
    code="""
import pandas as pd
from nodeflow import outputs, params

conn = params.get("connection", "")
query = params.get("query", "")
if conn and query:
    import sqlite3
    with sqlite3.connect(conn) as c:
        df = pd.read_sql_query(query, c)
else:
    df = pd.DataFrame({"id": [1, 2, 3], "value": [10, 20, 30]})
outputs.result = df
""".strip(),
)

_DATA_CLEANING = TemplateDef(
    file="data_cleaning",
    name="Data Cleaning",
    category="Cleaning",
    description="Drop missing values and duplicate rows.",
    inputs={"raw": ("dataframe", True)},
    outputs={"clean": "dataframe"},
    params={
        "dropna": {"type": "bool", "default": True},
        "drop_duplicates": {"type": "bool", "default": True},
    },
    code="""
from nodeflow import inputs, outputs, params

df = inputs.raw.copy()
if params.get("dropna", True):
    df = df.dropna()
if params.get("drop_duplicates", True):
    df = df.drop_duplicates()
outputs.clean = df.reset_index(drop=True)
""".strip(),
)

_SPLIT_DATA = TemplateDef(
    file="split_data",
    name="Split Data",
    category="Transform",
    description="Train/test split (stratified on the target when present).",
    inputs={"data": ("dataframe", True)},
    outputs={"train_df": "dataframe", "test_df": "dataframe"},
    params={
        "target": {"type": "str", "default": "target"},
        "test_size": {"type": "float", "default": 0.25},
    },
    code="""
from nodeflow import inputs, outputs, params
from sklearn.model_selection import train_test_split

df = inputs.data
target = params.get("target", "target")
strat = df[target] if target in df.columns else None
train_df, test_df = train_test_split(
    df, test_size=float(params.get("test_size", 0.25)), random_state=0, stratify=strat
)
outputs.train_df = train_df.reset_index(drop=True)
outputs.test_df = test_df.reset_index(drop=True)
""".strip(),
)


def _classifier_code(builder: str) -> str:
    return f"""
from nodeflow import inputs, outputs, params
from sklearn.metrics import accuracy_score

df = inputs.train_df
target = params.get("target", "target")
X = df.drop(columns=[target])
y = df[target]
{builder}
model.fit(X, y)
outputs.model = model
outputs.metrics = {{"train_accuracy": float(accuracy_score(y, model.predict(X)))}}
""".strip()


_LOGISTIC = TemplateDef(
    file="logistic_regression",
    name="Logistic Regression",
    category="Modeling",
    description="Train a logistic regression classifier.",
    inputs={"train_df": ("dataframe", True)},
    outputs={"model": "sklearn_model", "metrics": "dict"},
    params={"target": {"type": "str", "default": "target"}, "max_iter": {"type": "int", "default": 1000}},
    code=_classifier_code(
        "from sklearn.linear_model import LogisticRegression\n"
        "model = LogisticRegression(max_iter=int(params.get('max_iter', 1000)))"
    ),
)

_RANDOM_FOREST = TemplateDef(
    file="random_forest",
    name="Random Forest",
    category="Modeling",
    description="Train a random forest classifier.",
    inputs={"train_df": ("dataframe", True)},
    outputs={"model": "sklearn_model", "metrics": "dict"},
    params={
        "target": {"type": "str", "default": "target"},
        "n_estimators": {"type": "int", "default": 100},
        "max_depth": {"type": "int", "default": 5},
    },
    code=_classifier_code(
        "from sklearn.ensemble import RandomForestClassifier\n"
        "model = RandomForestClassifier(n_estimators=int(params.get('n_estimators', 100)),"
        " max_depth=int(params.get('max_depth', 5)), random_state=0)"
    ),
)

_XGBOOST = TemplateDef(
    file="xgboost_model",
    name="XGBoost",
    category="Modeling",
    description="Train an XGBoost classifier (falls back to sklearn GradientBoosting).",
    inputs={"train_df": ("dataframe", True)},
    outputs={"model": "sklearn_model", "metrics": "dict"},
    params={
        "target": {"type": "str", "default": "target"},
        "n_estimators": {"type": "int", "default": 100},
        "max_depth": {"type": "int", "default": 3},
    },
    code=_classifier_code(
        "try:\n"
        "    from xgboost import XGBClassifier\n"
        "    model = XGBClassifier(n_estimators=int(params.get('n_estimators', 100)),"
        " max_depth=int(params.get('max_depth', 3)), use_label_encoder=False,"
        " eval_metric='logloss', random_state=0)\n"
        "except Exception:\n"
        "    from sklearn.ensemble import GradientBoostingClassifier\n"
        "    model = GradientBoostingClassifier(n_estimators=int(params.get('n_estimators', 100)),"
        " max_depth=int(params.get('max_depth', 3)), random_state=0)"
    ),
)

_SHAP = TemplateDef(
    file="shap_explain",
    name="SHAP",
    category="Explainability",
    description="Explain a model (SHAP if available, else feature importances).",
    inputs={"model": ("sklearn_model", True), "data": ("dataframe", True)},
    outputs={"summary": "dataframe", "figure": "figure"},
    params={"target": {"type": "str", "default": "target"}},
    code="""
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from nodeflow import inputs, outputs, params

model = inputs.model
df = inputs.data
target = params.get("target", "target")
X = df.drop(columns=[target]) if target in df.columns else df

importance = None
try:
    import shap
    explainer = shap.Explainer(model, X)
    values = explainer(X)
    importance = np.abs(values.values).mean(axis=0)
except Exception:
    if hasattr(model, "feature_importances_"):
        importance = np.asarray(model.feature_importances_)
    elif hasattr(model, "coef_"):
        importance = np.abs(np.ravel(model.coef_))
    else:
        importance = np.zeros(X.shape[1])

summary = pd.DataFrame({"feature": list(X.columns), "importance": importance})
summary = summary.sort_values("importance", ascending=False).reset_index(drop=True)
outputs.summary = summary

fig = Figure(figsize=(5, 3))
ax = fig.add_subplot(1, 1, 1)
ax.barh(summary["feature"][::-1], summary["importance"][::-1])
ax.set_title("Feature importance")
outputs.figure = fig
""".strip(),
)

_EVALUATION = TemplateDef(
    file="evaluation",
    name="Evaluation",
    category="Evaluation",
    description="Evaluate a model on a test set; emit metrics + an HTML report.",
    inputs={"model": ("sklearn_model", True), "test_df": ("dataframe", True)},
    outputs={"metrics": "dict", "report": "html"},
    params={"target": {"type": "str", "default": "target"}},
    code="""
from nodeflow import inputs, outputs, params
from sklearn.metrics import accuracy_score, f1_score, classification_report

df = inputs.test_df
model = inputs.model
target = params.get("target", "target")
X = df.drop(columns=[target])
y = df[target]
pred = model.predict(X)

acc = float(accuracy_score(y, pred))
f1 = float(f1_score(y, pred, average="weighted"))
outputs.metrics = {"accuracy": acc, "f1": f1}
outputs.report = (
    "<h2>Evaluation</h2>"
    f"<p><b>Accuracy:</b> {acc:.3f}</p>"
    f"<p><b>F1 (weighted):</b> {f1:.3f}</p>"
    f"<pre>{classification_report(y, pred)}</pre>"
)
""".strip(),
)

_REPORT = TemplateDef(
    file="report",
    name="Report",
    category="Report",
    description="Combine up to three model evaluations into one HTML report.",
    inputs={
        "metrics_a": ("dict", False),
        "metrics_b": ("dict", False),
        "metrics_c": ("dict", False),
    },
    outputs={"report": "html"},
    params={
        "label_a": {"type": "str", "default": "Model A"},
        "label_b": {"type": "str", "default": "Model B"},
        "label_c": {"type": "str", "default": "Model C"},
    },
    code="""
from nodeflow import inputs, outputs, params

rows = []
for key, label_key in [("metrics_a", "label_a"), ("metrics_b", "label_b"), ("metrics_c", "label_c")]:
    m = inputs.get(key)
    if m:
        label = params.get(label_key, key)
        cells = "".join(f"<td>{k}={v:.3f}</td>" if isinstance(v, float) else f"<td>{k}={v}</td>"
                        for k, v in m.items())
        rows.append(f"<tr><th>{label}</th>{cells}</tr>")

outputs.report = "<h1>Model Comparison Report</h1><table border='1'>" + "".join(rows) + "</table>"
""".strip(),
)


TEMPLATE_DEFS: list[TemplateDef] = [
    _IMPORT_CSV, _SQL_QUERY, _DATA_CLEANING, _SPLIT_DATA,
    _LOGISTIC, _RANDOM_FOREST, _XGBOOST, _SHAP, _EVALUATION, _REPORT,
]


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
