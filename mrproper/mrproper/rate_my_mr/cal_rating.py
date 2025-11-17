"""
Comprehensive rating calculation for MR quality assessment.

NOTE: This CalRating class provides a more detailed rating system that includes
cyclomatic complexity and security scanning, but is NOT currently used in the
GitLab webhook integration (rate_my_mr_gitlab.py).

The webhook mode uses a simpler, faster cal_rating() function from rate_my_mr.py
to provide real-time feedback without the overhead of running Bandit security scans
and cyclomatic complexity analysis.

Future Enhancement: Consider integrating this comprehensive rating system if
execution time is acceptable for your workflow.
"""
from .utils import print_banner
from prettytable import PrettyTable
from .params import RMMWeights, RMMLimits

class CalRating:
    def __init__(self, data):
        self.data = data
        self.effective_rating = RMMWeights.TOTAL_WEIGHT.value
        self.table = PrettyTable()
    
    def rate_lint_disable(self, data):
        try:
            rating = RMMWeights.LINT_DISABLE.value
            if data.get("num_lint_disable") > 0:
                self.effective_rating -= RMMWeights.LINT_DISABLE.value
                rating = 0
            self.table.add_row(["Lint Disables", "0", data.get("num_lint_disable"), rating])
            return True, None
        except Exception as err:
            # print("------------")
            return False, str(err)
    
    def rate_max_loc(self, data):
        try:
            rating = RMMWeights.MAX_LOC.value
            if data.get("net_lines_of_code_change") > RMMLimits.MAX_LOC.value:
                self.effective_rating -= RMMWeights.MAX_LOC.value
                rating = 0
            self.table.add_row(["Lines of Code", f"<= {RMMLimits.MAX_LOC.value}", data.get("net_lines_of_code_change"), rating])
            return True, None
        except Exception as err:
            return False, str(err)

    def rate_cyclomatic_complexity(self, data):
        """
        Rate cyclomatic complexity based on average CC of modified/new methods.
        If avg_cc <= limit → full rating, else 0.
        """
        try:
            rating = RMMWeights.CYCLOMATIC_COMPLEXITY.value
            avg_cc = data.get("avg_cc", 0)

            if avg_cc > RMMLimits.CYCLOMATIC_COMPLEXITY.value:
                # exceeds threshold → deduct points
                self.effective_rating -= RMMWeights.CYCLOMATIC_COMPLEXITY.value
                rating = 0

            # Add row in report table
            self.table.add_row([
                "Cyclomatic Complexity",
                f"<= {RMMLimits.CYCLOMATIC_COMPLEXITY.value}",
                avg_cc,
                rating
            ])

            return True, None
        except Exception as err:
            return False, str(err)
    
    def rate_security_scan(self, data):
        """
        Rate security based on Bandit scan results.
        Rules:
        - If any HIGH issue in report → deduct full weight
        - Else if avg_security_scan_value > tolerance → deduct full weight
        - Else keep rating
        """
        try:
            rating = RMMWeights.SECURITY_SCAN.value
            avg_value = data.get("avg_security_scan_value", 0.0)
            report = data.get("security_report", {})

            # Check for high severity in the report
            high_issues = [
                issue for issue in report.get("results", [])
                if issue.get("issue_severity") == "HIGH"
            ]

            if high_issues or avg_value > RMMLimits.SECURITY_SCAN.value:
                self.effective_rating -= RMMWeights.SECURITY_SCAN.value
                rating = 0

            # Add row to table
            self.table.add_row([
                "Security Scan",
                f"<= {RMMLimits.SECURITY_SCAN.value:.4f} issues/LOC",
                f"{avg_value:.4f}",
                rating
            ])
            return True, None
        except Exception as err:
            return False, str(err)

    
    def cal_rating(self):
        try:
            print(self.data)
            print_banner("Effective Rating Report")
            self.table.field_names = ["Metric", "Expected", "Actual", "Rating"]
            for factor, value in self.data.items():
                if hasattr(self, f"rate_{factor.lower()}"):
                    # print("---------------")
                    # print(value)
                    success, error = getattr(self, f"rate_{factor.lower()}")(value)
                    if not success:
                        print(f"Error in rating {factor}: {error}")
                        return False, error
                # else:
                #     print(f"No rating method found for {factor}")
            self.table.add_row(["------------------", "----------", "--------", "--------"])
            self.table.add_row(["Effective rating",  RMMWeights.TOTAL_WEIGHT.value, "", max(self.effective_rating, 0)])
            print(self.table)
        except Exception as err:
            # print("===============")
            # print(str(err))
            return False, err

