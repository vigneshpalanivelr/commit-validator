
from enum import Enum


class RMMConstants(Enum):
    agent_url = "http://10.31.88.29:6006/generate"


class RMMLimits(Enum):
    MAX_LOC = 500


class RMMWeights(Enum):
    # make sure sum other weight should be equal to TOTAL_WEIGHT
    TOTAL_WEIGHT = 5
    MAX_LOC = 3
    LINT_DISABLE = 2
