from enum import Enum

class RMMConstants(Enum):
    agent_url = "http://10.31.88.29:6006/generate"

class RMMLimits(Enum):
    MAX_LOC = 500
    CYCLOMATIC_COMPLEXITY = 10
    SECURITY_SCAN = 0.005  # 1 issue per 200 LOC

class RMMWeights(Enum):
    # make sure sum other weight should be equal to TOTAL_WEIGHT
    TOTAL_WEIGHT = 5
    MAX_LOC = 1
    LINT_DISABLE = 1
    CYCLOMATIC_COMPLEXITY = 2
    SECURITY_SCAN = 1

class RMMChecks(Enum):
    MAX_LOC = "MAX_LOC"
    LINT_DISABLE = "LINT_DISABLE"
    CYCLOMATIC_COMPLEXITY = "CYCLOMATIC_COMPLEXITY"
    SECURITY_SCAN = "SECURITY_SCAN"

class RMMGenericView(Enum):
    MR_SUMMARY = "MR_SUMMARY"
    INITIAL_REVIEW = "INITIAL_REVIEW"

def get_all_applicable_checks():
    generic_views = [RMMGenericView.MR_SUMMARY.value, RMMGenericView.INITIAL_REVIEW.value]
    checks = [RMMChecks.MAX_LOC.value, RMMChecks.LINT_DISABLE.value, RMMChecks.CYCLOMATIC_COMPLEXITY.value, RMMChecks.SECURITY_SCAN.value]
    return generic_views + checks
