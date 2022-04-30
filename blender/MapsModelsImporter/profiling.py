# This file is part of SnapPortal
#
# Copyright (c) 2020-2021 -- Télécom Paris (Élie Michel <elie.michel@telecom-paris.fr>)
# 
# The MIT license:
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the “Software”), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# The Software is provided “as is”, without warranty of any kind, express or
# implied, including but not limited to the warranties of merchantability,
# fitness for a particular purpose and non-infringement. In no event shall the
# authors or copyright holders be liable for any claim, damages or other
# liability, whether in an action of contract, tort or otherwise, arising
# from, out of or in connection with the software or the use or other dealings
# in the Software.

# no bpy here

import time
from math import sqrt
from collections import defaultdict

# -------------------------------------------------------------------

class Timer():
    def __init__(self):
        self.start = time.perf_counter()

    def ellapsed(self):
        return time.perf_counter() - self.start

# -------------------------------------------------------------------

class ProfilingCounterProperty:
    def __init__(self):
        self.reset()

    def average(self):
        if self.sample_count == 0:
            return 0
        else:
            return self.accumulated / self.sample_count

    def stddev(self):
        if self.sample_count == 0:
            return 0
        else:
            avg = self.average()
            var = self.accumulated_sq / self.sample_count - avg * avg
            return sqrt(max(0, var))

    def add_sample(self, value):
        if hasattr(value, 'ellapsed'):
            value = value.ellapsed()
        self.sample_count += 1
        self.accumulated += value
        self.accumulated_sq += value * value

    def reset(self):
        self.sample_count = 0
        self.accumulated = 0.0
        self.accumulated_sq = 0.0

    def summary(self):
        """returns something like XXms (±Xms, X samples)"""
        return (
            f"{self.average()*1000.:.03}ms " +
            f"(±{self.stddev()*1000.:.03}ms, " +
            f"{self.sample_count} samples)"
        )

# -------------------------------------------------------------------

profiling_counters = defaultdict(ProfilingCounterProperty)
