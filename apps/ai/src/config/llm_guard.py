"""
Import guard for TrackGuard v4.2 LLM factory pattern.

Usage:
    Add this import at the top of agent files to enforce factory pattern:

    ```python
    from src.config.llm_guard import enforce_llm_factory
    enforce_llm_factory(__file__)
    ```

This module:
1. Scans the importing file for direct AzureOpenAI instantiation
2. Raises ImportError if found
3. Fails fast at import time (not runtime)

ONE RULE: All LLM calls MUST go through src/config/llm.py factory.
No direct AzureOpenAI instantiation in agents. Ever.
"""
import ast
import os


# Files that are allowed to import AzureOpenAI directly
ALLOWED_FILES = {
    'llm.py',  # The factory itself
    'llm_guard.py',  # This guard module
}


def enforce_llm_factory(file_path: str) -> None:
    """
    Enforce LLM factory pattern for the given file.

    Scans the file for direct AzureOpenAI instantiation and raises
    ImportError if found.

    Args:
        file_path: Path to the file being imported

    Raises:
        ImportError: If direct AzureOpenAI instantiation is detected

    Example:
        >>> from src.config.llm_guard import enforce_llm_factory
        >>> enforce_llm_factory(__file__)
    """
    filename = os.path.basename(file_path)

    # Skip allowed files
    if filename in ALLOWED_FILES:
        return

    # Read file content
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (IOError, OSError):
        # Can't read file, skip check
        return

    # Check for violations using AST
    violations = _scan_file_for_violations(content, file_path)

    if violations:
        raise ImportError(
            f"LLM Factory Pattern Violation in {filename}!\n"
            f"Direct AzureOpenAI instantiation detected: {violations[0]}\n\n"
            f"FIX: Use the factory pattern instead:\n"
            f"  from src.config.llm import get_llm_client\n"
            f"  client = get_llm_client()\n\n"
            f"See: apps/ai/src/config/llm.py"
        )


def _scan_file_for_violations(content: str, file_path: str) -> list[str]:
    """
    Scan file content for AzureOpenAI violations using AST.

    Args:
        content: File content to scan
        file_path: Path to the file (for error messages)

    Returns:
        List of violation descriptions
    """
    violations = []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        # Skip files with syntax errors
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check for AzureOpenAI() instantiation
            if isinstance(node.func, ast.Name) and node.func.id == "AzureOpenAI":
                violations.append(f"AzureOpenAI() at line {node.lineno}")
            # Check for OpenAI() instantiation (also not allowed)
            if isinstance(node.func, ast.Name) and node.func.id == "OpenAI":
                violations.append(f"OpenAI() at line {node.lineno}")

    return violations


def scan_directory_for_violations(directory: str) -> list[str]:
    """
    Scan a directory for LLM factory pattern violations.

    Useful for CI/CD checks or pre-commit hooks.

    Args:
        directory: Directory to scan

    Returns:
        List of file paths with violations
    """
    violations = []

    for root, _, files in os.walk(directory):
        for filename in files:
            if not filename.endswith('.py'):
                continue

            if filename in ALLOWED_FILES:
                continue

            file_path = os.path.join(root, filename)

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                file_violations = _scan_file_for_violations(content, file_path)
                if file_violations:
                    violations.append(file_path)
            except (IOError, OSError):
                continue

    return violations
