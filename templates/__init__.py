"""Built-in node templates.

Each template is a YAML node spec + a one-cell notebook (``inputs``/``outputs``
already wired). :func:`install_templates` materializes them into a project and
returns a populated :class:`~nodeflow.library.NodeLibrary`. Templates: Import CSV,
SQL Query, Data Cleaning, Split Data, Logistic Regression, Random Forest, XGBoost,
SHAP, Evaluation, Report.
"""

from __future__ import annotations

from .builtin import (
    TEMPLATE_DEFS,
    TemplateDef,
    build_spec,
    install_templates,
    template_specs,
)

__all__ = [
    "TEMPLATE_DEFS",
    "TemplateDef",
    "build_spec",
    "install_templates",
    "template_specs",
]
