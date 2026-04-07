import re
import tempfile
import os
from radon.raw import analyze
from prettytable import PrettyTable


class LOCCalculator:
    def __init__(self, diff_file):
        self.diff_file = diff_file

    def extract_modified_code(self):
        modified_code = []
        removed_code = []
        with open(self.diff_file, 'r') as file:
            for line in file:
                # Skip diff file headers (must come before +/- checks)
                if line.startswith('+++') or line.startswith('---'):
                    continue
                if line.startswith('+'):
                    modified_code.append(line[1:])  # Remove the '+' sign
                elif line.startswith('-'):
                    removed_code.append(line[1:])
        return ''.join(modified_code), "".join(removed_code)

    def _count_raw_lines(self, text):
        """
        Language-agnostic fallback: count non-empty, non-whitespace-only lines.
        Used when radon cannot parse the content (non-Python diffs).
        """
        return sum(1 for ln in text.splitlines() if ln.strip())

    def get_radon_raw_metrics(self, file_path):
        # Analyze the file and get the raw metrics
        with open(file_path, 'r') as file:
            code = file.read()

        # Analyze the code
        metrics = analyze(code)

        return metrics

    def calculate_loc(self):
        """
        Calculate lines of code from diff file using temporary files with proper cleanup.

        Returns:
            tuple: (success: bool, data: dict or error_message: str)
        """
        # Use NamedTemporaryFile with delete=False for thread safety and proper cleanup
        modified_file = None
        removed_file = None

        try:
            # Extract modified code from the diff output
            modified_code, removed_code = self.extract_modified_code()

            # Create temporary files with proper cleanup
            modified_file = tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.py',
                prefix='modified_code_',
                delete=False
            )
            modified_file.write(modified_code)
            modified_file.close()

            removed_file = tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.py',
                prefix='removed_code_',
                delete=False
            )
            removed_file.write(removed_code)
            removed_file.close()

            # Analyze the temporary files. radon.raw.analyze only handles
            # Python; for non-Python diffs (yaml/go/js/...) it raises
            # SyntaxError. Fall back to a simple non-empty line count so the
            # LOC metric remains meaningful for any language.
            try:
                added_sloc = self.get_radon_raw_metrics(modified_file.name).sloc
            except Exception:
                added_sloc = self._count_raw_lines(modified_code)

            try:
                removed_sloc = self.get_radon_raw_metrics(removed_file.name).sloc
            except Exception:
                removed_sloc = self._count_raw_lines(removed_code)

            # Shim objects so the rest of the function is unchanged
            class _M:
                def __init__(self, sloc):
                    self.sloc = sloc
            added_lines = _M(added_sloc)
            removed_lines = _M(removed_sloc)
            net_change = added_lines.sloc - removed_lines.sloc

            # Create a PrettyTable object
            table = PrettyTable()

            # Define the columns
            table.field_names = ["Metric", "Value"]

            # Add rows to the table
            table.add_row(["Lines of code added", added_lines.sloc])
            table.add_row(["Lines of code removed", removed_lines.sloc])
            table.add_row(["Net lines of code change", net_change])

            # Print the table
            print(table)

            return True, {
                'lines_of_code_added': added_lines.sloc,
                'lines_of_code_removed': removed_lines.sloc,
                'net_lines_of_code_change': net_change
            }
        except Exception as err:
            return False, str(err)
        finally:
            # Clean up temporary files
            if modified_file is not None:
                try:
                    os.unlink(modified_file.name)
                except Exception:
                    pass  # Ignore cleanup errors
            if removed_file is not None:
                try:
                    os.unlink(removed_file.name)
                except Exception:
                    pass  # Ignore cleanup errors

# loc_cal = LOCCalculator('diff_output2.txt')
# success, loc_data = loc_cal.calculate_loc()
# # print(loc_data)
