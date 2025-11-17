from enum import Enum
import os

class RMMConstants(Enum):
    # AI Service Configuration
    # ======================

    # Legacy direct AI service URL - can be overridden by AI_SERVICE_URL env var
    # Used when BFA_HOST is NOT configured
    agent_url = os.environ.get('AI_SERVICE_URL', 'http://10.31.88.29:6006/generate')

    # New LLM Adapter Configuration (used when BFA_HOST is set)
    # ======================
    # BFA_HOST: Hostname for the BFA intermediary service (e.g., "api-gateway.internal.com")
    # BFA_TOKEN_KEY: (Optional) Pre-configured JWT token - skips token API call if set
    # API_TIMEOUT: Timeout in seconds for LLM API calls (default: 120)
    # PROJECT_ID: Project identifier (set automatically by rate_my_mr_gitlab.py)
    # MR_IID: MR IID (set automatically by rate_my_mr_gitlab.py)
    #
    # When BFA_HOST is set, the system automatically uses the new LLM adapter
    # with JWT authentication instead of the legacy direct connection.

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
