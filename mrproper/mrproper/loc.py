import re
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
        try:
            # Extract modified code from the diff output
            modified_code, removed_code = self.extract_modified_code()

            # Save the modified code to a temporary file
            with open('modified_code.py', 'w') as temp_file:
                temp_file.write(modified_code)

            with open('removed_code.py', 'w') as temp_file:
                temp_file.write(removed_code)
            added_lines = self.get_radon_raw_metrics('modified_code.py')
            # print("Added lines info: {}".format(str(added_lines)))
            removed_lines = self.get_radon_raw_metrics('removed_code.py')
            # print("Removed lines info: {}".format(str(removed_lines)))
            net_change = added_lines.sloc - removed_lines.sloc

            # if success:
            # from prettytable import PrettyTable

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
            # else:
            #     print(f"Failed to calculate LOC: {loc_data}")

            return True, {
                'lines_of_code_added': added_lines.sloc,
                'lines_of_code_removed': removed_lines.sloc,
                'net_lines_of_code_change': net_change
            }
        except Exception as err:
            return False, str(err)

# loc_cal = LOCCalculator('diff_output2.txt')
# success, loc_data = loc_cal.calculate_loc()
# # print(loc_data)
