"""Midas brief — density-adaptive brief composition.

Produces decision briefs at varying density levels based on regime band,
dollar-impact, and model confidence. Ranges from compressed one-liners
for routine decisions to extreme-weight briefs with OOD warnings.
"""

from midas.brief.composer import BriefComposer
from midas.brief.density_matrix import DensityMatrix
from midas.brief.templates import BriefTemplates
from midas.brief.top_of_fold import TopOfFoldCard

__all__ = [
    "BriefComposer",
    "BriefTemplates",
    "DensityMatrix",
    "TopOfFoldCard",
]
