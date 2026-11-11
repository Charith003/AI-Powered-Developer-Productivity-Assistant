import ast

from app.test_generation.schemas import PlannedCase


def plan_python(source: str, categories: list[str], regression_context: str = ""):
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"Source syntax is invalid at line {exc.lineno}") from exc
    functions: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            if not node.name.startswith("_"):
                functions.append((node.name, node))
            self.generic_visit(node)

        visit_AsyncFunctionDef = visit_FunctionDef

    Visitor().visit(tree)
    if not functions:
        raise ValueError("No public Python functions or methods were found")
    imports = sorted(
        {
            alias.name.split(".")[0]
            for item in ast.walk(tree)
            if isinstance(item, ast.Import)
            for alias in item.names
        }
        | {
            item.module.split(".")[0]
            for item in ast.walk(tree)
            if isinstance(item, ast.ImportFrom) and item.module
        }
    )
    output: list[PlannedCase] = []
    for name, node in functions[:20]:
        args = [arg.arg for arg in node.args.args if arg.arg not in {"self", "cls"}]
        nodes = list(ast.walk(node))
        return_type = ast.unparse(node.returns) if node.returns is not None else "not annotated"
        raised = sorted(
            {
                ast.unparse(item.exc.func if isinstance(item.exc, ast.Call) else item.exc)
                for item in nodes
                if isinstance(item, ast.Raise) and item.exc is not None
            }
        )
        detail = (
            f"Parameters: {', '.join(args) if args else 'none'}; return annotation: {return_type}; "
            f"explicit exceptions: {', '.join(raised) if raised else 'none detected'}; source line {node.lineno}."
        )
        relevant = {"normal"}
        if args:
            relevant.add("boundary")
        if any(isinstance(item, ast.Raise) for item in nodes):
            relevant.add("exception")
        if any(isinstance(item, ast.If) for item in nodes) or any(
            isinstance(item, ast.Call)
            and isinstance(item.func, ast.Name)
            and item.func.id == "isinstance"
            for item in nodes
        ):
            relevant.add("negative")
        if regression_context.strip():
            relevant.add("regression")
        selected = [category for category in categories if category in relevant]
        for category in selected or ["normal"]:
            objective = {
                "normal": "Verify representative valid input and the documented return behavior.",
                "boundary": "Probe relevant empty, zero, minimum, maximum, or length boundaries.",
                "negative": "Check invalid or unexpected values are rejected or handled safely.",
                "exception": "Verify an exception is raised or dependency failure is handled when source behavior supports it.",
                "regression": regression_context
                or "Exercise the linked code-review finding as a regression scenario.",
            }[category]
            output.append(
                PlannedCase(
                    target=name,
                    objective=f"{objective} {detail}",
                    category=category,
                    input_data=f"Provide values for: {', '.join(args)}"
                    if args
                    else "Call without arguments.",
                    expected_result="Derive assertion from source contract; do not assume undocumented behavior.",
                    dependencies_or_mocks=imports[:12] or ["No module imports were detected."],
                    priority="high" if category in {"normal", "regression"} else "medium",
                )
            )
    return output
