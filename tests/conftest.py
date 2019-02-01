#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Read more about conftest.py under:
    https://pytest.org/latest/plugins.html
"""

# import pytest
import sys
from pathlib import Path
import shutil
import os
import pytest

root = Path(__file__).parent.parent
sys.path.append(str(root / "src"))
