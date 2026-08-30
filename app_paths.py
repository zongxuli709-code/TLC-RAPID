# -*- coding: utf-8 -*-
"""统一解析程序根目录：开发时用源码目录，打包成 exe 后用 exe 所在目录。"""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent
