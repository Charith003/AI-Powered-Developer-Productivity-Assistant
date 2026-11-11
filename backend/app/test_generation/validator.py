import ast
import re

UNSAFE_PATTERNS = [
    re.compile(r"\b(subprocess\.(?:run|Popen|call)|os\.system|eval|exec)\s*\("),
    re.compile(r"\b(socket|urllib\.request|requests\.)"),
    re.compile(r"\b(fork|forkbomb)\b", re.IGNORECASE),
]


def validate_python_test(test_code: str, source_path: str) -> list[str]:
    errors = []
    try:
        tree = ast.parse(test_code, filename="test_generated.py")
        compile(tree, "test_generated.py", "exec")
    except (SyntaxError, ValueError) as exc:
        return [f"Syntax validation failed: {getattr(exc, 'msg', str(exc))}"]
    test_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]
    if not test_functions:
        errors.append("No pytest test functions were discovered statically")
    names = [node.name for node in test_functions]
    if len(set(names)) != len(names):
        errors.append("Duplicate pytest function names were found")
    bodies = [ast.dump(node, include_attributes=False) for node in test_functions]
    if len(set(bodies)) != len(bodies):
        errors.append("Duplicate pytest test bodies were found")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.While)
            and isinstance(node.test, ast.Constant)
            and node.test.value is True
        ):
            errors.append("Generated code contains an unbounded while-true loop")
            break
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "range"
            and any(
                isinstance(arg, ast.Constant)
                and isinstance(arg.value, int)
                and abs(arg.value) > 10_000_000
                for arg in node.args
            )
        ):
            errors.append("Generated code contains a very large range loop")
            break
        if isinstance(node, ast.Assert):
            expression = node.test
            if isinstance(expression, ast.Constant) and expression.value is True:
                errors.append("Generated code contains a tautological assertion")
                break
            if isinstance(expression, ast.Compare) and len(expression.ops) == 1:
                left = ast.dump(expression.left, include_attributes=False)
                right = ast.dump(expression.comparators[0], include_attributes=False)
                if left == right:
                    errors.append(
                        "Generated code contains an assertion comparing an expression to itself"
                    )
                    break
    for pattern in UNSAFE_PATTERNS:
        if pattern.search(test_code):
            errors.append(
                "Generated code uses a blocked process, dynamic execution, or network API"
            )
            break
    imports = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imports.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    expected_module = (
        source_path.rsplit(".", 1)[0].replace("/", ".").replace("\\", ".").split(".")[-1]
    )
    if expected_module not in imports:
        errors.append(f"Generated test does not import the target module '{expected_module}'")
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    if test_functions and not any(isinstance(node, ast.Assert) for node in ast.walk(tree)):
        errors.append("Generated tests contain no assertions")
    if test_functions and not calls:
        errors.append("Generated tests do not call the target code")
    return list(dict.fromkeys(errors))
