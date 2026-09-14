"""Compare model_state before/after forced validation rollback for red ops."""

from __future__ import annotations

from tests.native_model_state import model_state


def _diff(before, after) -> list[str]:
    lines: list[str] = []
    before_map = {entry[0]: entry for entry in before}
    after_map = {entry[0]: entry for entry in after}
    for name in sorted(set(before_map) | set(after_map)):
        if name not in before_map:
            lines.append(f"+ object {name}")
            continue
        if name not in after_map:
            lines.append(f"- object {name}")
            continue
        b = before_map[name]
        a = after_map[name]
        if b[1] != a[1]:
            lines.append(f"{name}: TypeId {b[1]!r} -> {a[1]!r}")
        if b[2] != a[2]:
            lines.append(f"{name}: State {b[2]!r} -> {a[2]!r}")
        if b[3] != a[3]:
            lines.append(f"{name}: InList {b[3]!r} -> {a[3]!r}")
        if b[4] != a[4]:
            lines.append(f"{name}: OutList {b[4]!r} -> {a[4]!r}")
        b_props = {item[0]: item for item in b[5]}
        a_props = {item[0]: item for item in a[5]}
        for prop in sorted(set(b_props) | set(a_props)):
            if prop not in b_props:
                lines.append(f"{name}.{prop}: added")
                continue
            if prop not in a_props:
                lines.append(f"{name}.{prop}: removed")
                continue
            if b_props[prop] != a_props[prop]:
                lines.append(f"{name}.{prop}: {b_props[prop]!r} -> {a_props[prop]!r}")
    return lines


def _first_property_diff(before, after) -> str | None:
    before_map = {entry[0]: entry for entry in before}
    after_map = {entry[0]: entry for entry in after}
    for name in sorted(set(before_map) | set(after_map)):
        if name not in before_map or name not in after_map:
            return f"{name}: object presence"
        b = before_map[name]
        a = after_map[name]
        if b[1] != a[1]:
            return f"{name}: TypeId"
        if b[2] != a[2]:
            return f"{name}: State"
        if b[3] != a[3]:
            return f"{name}: InList"
        if b[4] != a[4]:
            return f"{name}: OutList"
        b_props = {item[0]: item for item in b[5]}
        a_props = {item[0]: item for item in a[5]}
        for prop in sorted(set(b_props) | set(a_props)):
            if prop not in b_props:
                return f"{name}.{prop}: added"
            if prop not in a_props:
                return f"{name}.{prop}: removed"
            if b_props[prop] != a_props[prop]:
                b_hash = b_props[prop][4]
                a_hash = a_props[prop][4]
                return f"{name}.{prop}: hash {b_hash!r} -> {a_hash!r}"
    return None


def _run(op: str, kind: str, base: dict[str, object]) -> None:
    import FreeCAD
    from tests.typed_feature_native_matrix import _run as invoke
    from tests.typed_feature_native_matrix import collaborators, revision_state
    from tests.typed_feature_native_setup import prepare_native_document, run_kwargs

    document = FreeCAD.newDocument(f"Diag{op}")
    try:
        prepare_native_document(document, kind)
        document.recompute()
        before = model_state(document), revision_state(document, op)
        result = invoke(
            op,
            collaborators(
                FreeCAD,
                lambda _document: (_ for _ in ()).throw(RuntimeError("forced validation failure")),
            ),
            document.Name,
            base,
        )
        after = model_state(document), revision_state(document, op)
        print(f"===== {op} success={result.get('success')} code={result.get('error_code')} =====")
        if before == after:
            print("settled_state: match")
        elif before[0] == after[0]:
            print("model_state: match")
            print("revision_state: DIFF", len(before[1]), len(after[1]))
        else:
            print("settled_state: DIFF")
            first = _first_property_diff(before[0], after[0])
            if first:
                print(f" first_property_mismatch: {first}")
            for line in _diff(before[0], after[0])[:40]:
                print(" ", line)
        if before[1] != after[1]:
            print("revision_state: DIFF", len(before[1]), len(after[1]))
    finally:
        FreeCAD.closeDocument(document.Name)


def main() -> None:
    _run(
        "boolean_union",
        "boolean",
        {"doc_name": "Doc", "shape1": "Shape1", "shape2": "Shape2", "result_name": "Result"},
    )
    _run(
        "pad_feature",
        "profile",
        {
            "doc_name": "Doc",
            "sketch_name": "Sketch",
            "pad_name": "Pad",
            "length": 10.0,
            "body_name": "Body",
        },
    )
    _run(
        "loft_feature",
        "loft",
        {
            "doc_name": "Doc",
            "sketch_names": ["Sketch1", "Sketch2"],
            "loft_name": "Loft",
            "body_name": None,
            "ruled": False,
            "closed": False,
        },
    )
    _run(
        "chamfer_feature",
        "edge_feature",
        {
            "doc_name": "Doc",
            "base_feature": "Pad",
            "chamfer_name": "Chamfer",
            "size": 1.0,
            "edge_refs": None,
            "body_name": None,
        },
    )


if __name__ == "__main__":
    main()
