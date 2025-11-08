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
                # Check for the start of a code block
                if line.startswith('+++') or line.startswith('---'):
                    continue
                if line.startswith('+') and not line.startswith('+++'):
                    modified_code.append(line[1:])  # Remove the '+' sign
                if line.startswith("-"):
                    removed_code.append(line[1:])
        return ''.join(modified_code), "".join(removed_code)

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

            # Analyze the temporary files
            added_lines = self.get_radon_raw_metrics(modified_file.name)
            removed_lines = self.get_radon_raw_metrics(removed_file.name)
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
