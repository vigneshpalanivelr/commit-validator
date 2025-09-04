import re

class CyclomaticComplexityCalculator:
    """
    Calculates cyclomatic complexity from a git diff file.
    - For newly added functions: compute CC of full function body
    - For modified functions: rebuild the full function body post-change and compute CC
    """

    def __init__(self, diff_file):
        self.diff_file = diff_file

    def _calculate_cc(self, func_body_lines):
        """
        Simple CC calculation:
        Base = 1
        +1 for each decision point (if, for, while, case, &&, ||, except, elif)
        """
        code = "\n".join(func_body_lines)
        decisions = re.findall(
            r"\b(if|for|while|elif|case|catch|except)\b|(\&\&|\|\|)", code
        )
        return 1 + len(decisions)

    def _extract_functions(self, diff_lines):
        """
        Extract modified/new function bodies from diff.
        - Collect lines after 'def ' (Python-style, can extend to other langs)
        - Ignore removed lines (-), keep added (+) and unchanged ( )
        """
        functions = []
        inside_func = False
        current_func = []
        indent_level = None
        func_name = None

        for line in diff_lines:
            raw_line = line[1:] if line.startswith(("+", "-", " ")) else line

            # Detect function signature
            match = re.match(r"^\s*def\s+(\w+)\(", raw_line)
            if match:
                # Save previous function if exists
                if current_func:
                    functions.append((func_name, current_func))

                inside_func = True
                func_name = match.group(1)
                current_func = [raw_line]
                indent_level = None
                continue

            if inside_func:
                # Skip removed lines (starting with -)
                if line.startswith("-"):
                    continue

                # Capture added (+) or unchanged ( )
                code_line = raw_line
                if code_line.strip() == "":
                    current_func.append(code_line)
                    continue

                # Track indentation to know when func ends
                leading_spaces = len(code_line) - len(code_line.lstrip())
                if indent_level is None and code_line.strip():
                    indent_level = leading_spaces

                # If indent falls back to 0 and not blank → func ends
                if indent_level is not None and leading_spaces == 0 and not code_line.strip().startswith("def"):
                    functions.append((func_name, current_func))
                    current_func = []
                    inside_func = False
                    func_name = None
                else:
                    current_func.append(code_line)

        if current_func and func_name:
            functions.append((func_name, current_func))

        return functions

    def analyze(self):
        """
        Main entry:
        - Parse diff file
        - Extract modified/new functions
        - Compute CC per function (post-patch version)
        - Return dict: { 'avg_cc': ..., 'method_wise_cc': {...} }
        """
        with open(self.diff_file, "r") as f:
            diff_lines = f.readlines()

        functions = self._extract_functions(diff_lines)

        if not functions:
            return {"avg_cc": 0, "method_wise_cc": {}}

        method_wise_cc = {}
        cc_values = []

        for func_name, func in functions:
            cc = self._calculate_cc(func)
            method_wise_cc[func_name] = cc
            cc_values.append(cc)

        avg_cc = int(sum(cc_values) / len(cc_values))

        return True, {
            "avg_cc": avg_cc,
            "method_wise_cc": method_wise_cc
        }

