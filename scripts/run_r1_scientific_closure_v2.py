#!/usr/bin/env python3
from __future__ import annotations

import pantheon_cross_platform
import run_r1_scientific_closure as closure


if __name__ == '__main__':
    pantheon_cross_platform.install()
    raise SystemExit(closure.main())
