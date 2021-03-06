# SPDX-License-Identifier: MIT
# Copyright (c) 2020-2021: PySAGES contributors
# See LICENSE.md and CONTRIBUTORS.md at https://github.com/SSAGESLabs/PySAGES


import jax.numpy as np

from collections import namedtuple


class Box(namedtuple("Box", ("H", "origin"))):
    def __new__(cls, H, origin):
        return super().__new__(cls, np.asarray(H), np.asarray(origin))
    #
    def __repr__(self):
        return repr("PySAGES " + type(self).__name__)


class Snapshot(
    namedtuple(
        "Snapshot",
        ("positions", "vel_mass", "forces", "ids", "box", "dt")
    )
):
    def __repr__(self):
        return repr("PySAGES " + type(self).__name__)
