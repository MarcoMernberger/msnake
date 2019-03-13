#!/usr/bin/python3
import hashlib
import os
from pathlib import Path

dockerfile = Path(__file__).parent / 'Dockerfile'
tag = hashlib.md5(dockerfile.read_bytes()).hexdigest()

os.system('docker build -t mbf_anysnake_18.04:%s .' % tag)

