"""Extract declarative TVB `neotraits` class attributes from `griffe` AST expressions."""

from __future__ import annotations

import ast
from dataclasses import dataclass

import griffe

TRAIT_CLASSES = frozenset(
    {
        "Attr",
        "NArray",
        "Final",
        "Float",
        "Int",
        "List",
        "EnumAttr",
        "Dim",
    }
)


@dataclass(frozen=True)
class TraitInfo:
    """Structured metadata extracted from a declarative `neotraits` attribute."""

    name: str
    trait_kind: str
    type_expr: str
    default_expr: str
    domain_expr: str
    required: str
    label: str
    doc: str
    lineno: int | None = None


def _eval_string_literal(expr: griffe.Expr | str | None) -> str:
    """Safely extract clean text from a Python string expression node."""
    if expr is None:
        return ""
    raw = str(expr).strip()
    try:
        val = ast.literal_eval(raw)
        if isinstance(val, str):
            return " ".join(val.split())
    except Exception:
        pass
    return " ".join(raw.strip("'\"").split())


def _expr_head_name(expr: griffe.Expr) -> str:
    """Return the terminal callable name for an `ExprCall.function`."""
    fn = getattr(expr, "function", None)
    if fn is None:
        return ""
    name = getattr(fn, "name", None)
    if name:
        return str(name)
    return str(fn).rsplit(".", 1)[-1]


def _format_domain(expr: griffe.Expr | None) -> str:
    """Format `Range(...)`, `LinspaceRange(...)`, or `choices` expressions cleanly."""
    if expr is None:
        return "—"
    raw = " ".join(str(expr).split())
    return raw if raw else "—"


def _format_default(expr: griffe.Expr | None) -> str:
    """Format default value expressions cleanly, stripping `numpy.` noise if concise."""
    if expr is None:
        return "—"
    raw = " ".join(str(expr).split())
    raw = raw.replace("numpy.array(", "np.array(")
    return raw if raw else "—"


def extract_trait(attr: griffe.Attribute) -> TraitInfo | None:
    """Inspect a `griffe.Attribute`; return `TraitInfo` if it declares a `neotraits` descriptor."""
    val = getattr(attr, "value", None)
    if not isinstance(val, griffe.ExprCall):
        return None

    head = _expr_head_name(val)
    if head not in TRAIT_CLASSES:
        return None

    kwargs: dict[str, griffe.Expr] = {}
    positional: list[griffe.Expr] = []
    for arg in val.arguments:
        if isinstance(arg, griffe.ExprKeyword):
            kwargs[arg.name] = arg.value
        else:
            positional.append(arg)

    # Positional args: Attr(field_type, default=..., ...), List(of, ...), Float/Int(...)
    field_type = kwargs.get("field_type") or kwargs.get("dtype") or kwargs.get("of")
    if field_type is None and positional:
        field_type = positional[0]

    if head == "NArray":
        dtype_expr = kwargs.get("dtype")
        type_str = f"ndarray[{dtype_expr}]" if dtype_expr is not None else "ndarray[float]"
    elif head == "List":
        of_expr = field_type
        type_str = f"list[{of_expr}]" if of_expr is not None else "list"
    elif head == "Float":
        type_str = str(field_type) if field_type is not None else "float"
    elif head == "Int":
        type_str = str(field_type) if field_type is not None else "int"
    elif head == "Final":
        type_str = f"Final[{field_type}]" if field_type is not None else "Final"
    else:
        type_str = str(field_type) if field_type is not None else head

    default_expr = kwargs.get("default")
    if default_expr is None and head == "Attr" and len(positional) >= 2:
        default_expr = positional[1]

    domain_expr = kwargs.get("domain") or kwargs.get("choices")
    req_expr = kwargs.get("required")
    req_str = str(req_expr) if req_expr is not None else ("True" if head == "Attr" else "True")

    label = _eval_string_literal(kwargs.get("label"))
    doc = _eval_string_literal(kwargs.get("doc"))

    return TraitInfo(
        name=attr.name,
        trait_kind=head,
        type_expr=type_str,
        default_expr=_format_default(default_expr),
        domain_expr=_format_domain(domain_expr),
        required=req_str,
        label=label,
        doc=doc,
        lineno=attr.lineno,
    )


def class_is_has_traits(cls: griffe.Class) -> bool:
    """Return True if `cls` inherits from `HasTraits` or declares `neotraits` descriptors."""
    for base in cls.bases:
        if "HasTraits" in str(base) or "Model" in str(base):
            return True
    try:
        for rbase in cls.resolved_bases:
            if rbase.name == "HasTraits" or "neotraits" in rbase.canonical_path:
                return True
    except Exception:
        pass
    for member in cls.members.values():
        if isinstance(member, griffe.Attribute) and extract_trait(member) is not None:
            return True
    return False
