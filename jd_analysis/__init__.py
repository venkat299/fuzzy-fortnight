from __future__ import annotations  # Re-export jd_analysis public API

from .jd_analysis import (  # noqa: F401 F403
    CompetencyArea,
    CompetencyMatrix,
    JobProfile,
    analyze_with_config,
    generate_competency_matrix,
)

__all__ = [
    "CompetencyArea",
    "CompetencyMatrix",
    "JobProfile",
    "analyze_with_config",
    "generate_competency_matrix",
]
