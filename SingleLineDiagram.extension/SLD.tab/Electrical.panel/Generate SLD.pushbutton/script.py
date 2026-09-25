# -*- coding: utf-8 -*-
"""Generate a single line diagram of the electrical equipment
(panels, switchboards, transformers) and the feeders between them."""
__title__ = "Generate\nSLD"

from sld.command import run

run(include_branch_circuits=False)
