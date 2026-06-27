"""Node specifications parsed from YAML.

A *node spec* is the declarative interface of a node: its name/category, the
notebook that backs it, its typed input/output ports, its parameters, and its
execution environment. Specs live in standalone YAML files so they are easy to
author, diff, and ship as templates.

    name: Train RF
    category: Modeling
    notebook: notebooks/train_rf.ipynb
    inputs:
      train_df:
        type: dataframe
    outputs:
      model:
        type: sklearn_model
    parameters:
      max_depth:
        type: int
        default: 5
    environment:
      conda_env: default

Parsing is strict (`extra: forbid`) so typos in keys are caught early, and
parameter defaults are validated against their declared types.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator


class NodeSpecError(ValueError):
    """Raised when a node spec is malformed or fails validation."""


class ParameterType(str, Enum):
    INT = "int"
    FLOAT = "float"
    STR = "str"
    BOOL = "bool"
    CHOICE = "choice"


class ParameterSpec(BaseModel):
    """A user-tunable parameter injected into the notebook."""

    model_config = ConfigDict(extra="forbid")

    type: ParameterType
    default: Any = None
    description: str = ""
    choices: list[Any] | None = None
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def _check_default(self) -> ParameterSpec:
        t, d = self.type, self.default
        if t is ParameterType.CHOICE:
            if not self.choices:
                raise ValueError("a 'choice' parameter must define non-empty 'choices'")
            if d is not None and d not in self.choices:
                raise ValueError(f"default {d!r} is not one of choices {self.choices!r}")
            return self
        if d is None:
            return self  # no default => required at runtime
        ok = {
            ParameterType.INT: isinstance(d, int) and not isinstance(d, bool),
            ParameterType.FLOAT: isinstance(d, (int, float)) and not isinstance(d, bool),
            ParameterType.STR: isinstance(d, str),
            ParameterType.BOOL: isinstance(d, bool),
        }[t]
        if not ok:
            raise ValueError(f"default {d!r} is not compatible with type {t.value!r}")
        if t is ParameterType.FLOAT and isinstance(d, int):
            self.default = float(d)
        return self


class PortSpec(BaseModel):
    """A typed input or output port."""

    model_config = ConfigDict(extra="forbid")

    type: str
    description: str = ""
    required: bool = True

    @model_validator(mode="after")
    def _check_type(self) -> PortSpec:
        if not isinstance(self.type, str) or not self.type.strip():
            raise ValueError("port 'type' must be a non-empty string")
        return self


class EnvironmentSpec(BaseModel):
    """How/where the node's notebook should execute."""

    model_config = ConfigDict(extra="forbid")

    conda_env: str = "default"
    kernel: str | None = None
    python: str | None = None
    pip: list[str] = []


class NodeSpec(BaseModel):
    """The full declarative interface of a node."""

    model_config = ConfigDict(extra="forbid")

    name: str
    category: str = "General"
    description: str = ""
    notebook: str | None = None
    inputs: dict[str, PortSpec] = {}
    outputs: dict[str, PortSpec] = {}
    parameters: dict[str, ParameterSpec] = {}
    environment: EnvironmentSpec = EnvironmentSpec()

    # -- convenience ------------------------------------------------------
    def default_params(self) -> dict[str, Any]:
        """The default value of every parameter (``None`` if undeclared)."""
        return {name: p.default for name, p in self.parameters.items()}

    def input_type(self, name: str) -> str:
        return self.inputs[name].type

    def output_type(self, name: str) -> str:
        return self.outputs[name].type

    def required_inputs(self) -> list[str]:
        return [n for n, p in self.inputs.items() if p.required]


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def parse_node_spec(text: str, *, source: str = "<string>") -> NodeSpec:
    """Parse a node spec from YAML text. Raises :class:`NodeSpecError`."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise NodeSpecError(f"invalid YAML in {source}: {exc}") from exc
    if data is None:
        raise NodeSpecError(f"node spec {source} is empty")
    if not isinstance(data, dict):
        raise NodeSpecError(f"node spec {source} must be a mapping, got {type(data).__name__}")
    try:
        return NodeSpec.model_validate(data)
    except ValidationError as exc:
        raise NodeSpecError(f"invalid node spec {source}:\n{exc}") from exc


def load_node_spec(path: str | Path) -> NodeSpec:
    """Load and validate a node spec from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise NodeSpecError(f"node spec file not found: {path}")
    return parse_node_spec(path.read_text(), source=str(path))


def dump_node_spec(spec: NodeSpec) -> str:
    """Serialize a node spec back to YAML (useful for templates/tests)."""
    data = spec.model_dump(exclude_defaults=False, mode="json")
    return yaml.safe_dump(data, sort_keys=False)
