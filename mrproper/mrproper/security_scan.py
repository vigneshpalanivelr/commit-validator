import json
import subprocess
import tempfile
import os
import re

class SecurityScanner:
    """
    Runs Bandit on a file/directory and collects security issues.
    """

    def __init__(self, target):
        """
        Args:
            target (str): file or directory path to run Bandit on
            tolerance (float): max issues/LOC allowed (default 0.005 => 1 issue per 200 LOC)
        """
        self.diff_file = target
    
    def extract_added_code_from_diff(self):
        """
        Extract newly added Python code from diff and write into a temp .py file.
        - Newly added methods (all lines with '+') are preserved as-is.
        - All other '+' lines are stripped of indentation and wrapped in a dummy function.
        Returns the path to the temporary .py file.
        """
        code_blocks = []
        dummy_lines = []
        current_method = []
        inside_method = False
        inside_docstring = False
        method_indent_level = None

        # Regex to detect method/function definitions
        method_def_regex = re.compile(r'^\s*def\s+(\w+)\s*\(.*\)\s*(->\s*[\w\[\]]+\s*)?:')

        try:
            with open(self.diff_file, "r") as f:
                diff_lines = f.readlines()
        except FileNotFoundError:
            return ""

        i = 0
        while i < len(diff_lines):
            line = diff_lines[i]
            # Skip non-added lines or diff metadata
            if not line.startswith("+") or line.startswith("+++"):
                i += 1
                continue

            content = line[1:].rstrip()  # Strip leading "+" and trailing whitespace
            stripped = content.strip()

            # Skip empty lines
            if not stripped:
                if inside_method:
                    current_method.append(content)
                i += 1
                continue

            # Calculate indentation level (excluding "+")
            leading_spaces = len(line) - len(line.lstrip()) - 1

            # Handle docstrings
            if stripped.startswith(('"""', "'''")):
                if inside_docstring:
                    inside_docstring = False
                else:
                    inside_docstring = True
                if inside_method:
                    current_method.append(content)
                i += 1
                continue
            if inside_docstring and inside_method:
                current_method.append(content)
                i += 1
                continue

            # Detect method definition
            match = method_def_regex.match(stripped)
            if match and not inside_method:
                # Flush previous method
                if current_method:
                    code_blocks.append("\n".join(current_method))
                    current_method = []
                
                # Start new method
                inside_method = True
                method_indent_level = leading_spaces
                current_method = [content]
                i += 1
                continue

            if inside_method:
                # Include lines in method if indented or comment/empty
                if leading_spaces > method_indent_level or stripped.startswith('#') or not stripped:
                    current_method.append(content)
                else:
                    # End of method
                    code_blocks.append("\n".join(current_method))
                    current_method = []
                    inside_method = False
                    method_indent_level = None
                    # Handle current line as non-method code
                    if not stripped.startswith(('@param', '@return')):
                        dummy_lines.append(stripped)  # Strip indentation
            else:
                # Non-method line
                if not stripped.startswith(('@param', '@return')):
                    dummy_lines.append(stripped)  # Strip indentation
            
            i += 1

        # Flush any remaining method
        if current_method:
            code_blocks.append("\n".join(current_method))

        # Add dummy function with non-method lines
        if dummy_lines:
            code_blocks.append("def __bandit_dummy__():\n" + "\n".join(f"    {line}" for line in dummy_lines))

        # Filter out empty blocks and join with double newlines
        code_blocks = [block for block in code_blocks if block.strip()]
        final_code = "\n\n".join(code_blocks)

        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".py", delete=False) as tmp_file:
            tmp_file.write(final_code + "\n")
            tmp_file_name = tmp_file.name

        return tmp_file_name

    def _run_bandit(self):
        """Run Bandit scan and return JSON result dict."""
        # print("test")
        # print(self.diff_file)

        # If no file provided, return empty report
        if not self.diff_file:
            return False, {
                "avg_security_scan_value": 0.0,
                "severity_count": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
                "security_report": {"results": [], "metrics": {}, "errors": []}
            }

        try:
            result = subprocess.run(
                ["bandit", "-f", "json", "-q", self.diff_file],
                capture_output=True,
                text=True
            )

            # Handle Bandit exit codes
            if result.returncode in (0, 1):  
                # 0 = no issues, 1 = issues found (normal cases)
                try:
                    data = json.loads(result.stdout)
                except json.JSONDecodeError:
                    print("Bandit output not JSON decodable:", result.stdout)
                    return False, {
                        "avg_security_scan_value": 0.0,
                        "severity_count": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
                        "security_report": {"results": [], "metrics": {}, "errors": [result.stdout]}
                    }

                return True, data

            else:
                # 2 or anything else = real execution error
                print("Bandit failed to run:", result.stderr)
                return False, {
                    "avg_security_scan_value": 0.0,
                    "severity_count": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
                    "security_report": {"results": [], "metrics": {}, "errors": [result.stderr]}
                }

        except Exception as e:
            return False, {
                "avg_security_scan_value": 0.0,
                "severity_count": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
                "security_report": {"results": [], "metrics": {}, "errors": [str(e)]}
            }
        # finally:
        #     if os.path.exists(py_file):
        #     os.remove(py_file)

    def analyze(self):
        """
        Run Bandit scan and return dict with metrics (NO score calculation here).
        {
            "security_scan": {
                "avg_security_scan_value": float,
                "severity_count": {"HIGH": int, "MEDIUM": int, "LOW": int},
                "security_report": {... full JSON ...}
            }
        }
        """
        success, data = self._run_bandit()
        if not success:
            return False, {
                "security_scan": {
                    "avg_security_scan_value": 0,
                    "severity_count": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
                    "security_report": {"error": data}
                }
            }

        issues = data.get("results", [])
        metrics = data.get("metrics", {})

        # safer LOC fetch
        file_metrics = metrics.get(self.diff_file, metrics.get("_totals", {}))
        loc = file_metrics.get("loc", 0) or 1

        # Count severity
        severity_count = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for issue in issues:
            sev = issue.get("issue_severity")
            if sev in severity_count:
                severity_count[sev] += 1

        total_issues = sum(severity_count.values())
        avg_issues_per_loc = total_issues / loc

        return True, {
                "avg_security_scan_value": avg_issues_per_loc,
                "severity_count": severity_count,
                "security_report": data
            }
