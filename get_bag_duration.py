#!/usr/bin/env python3
import sys
from rosbags.highlevel import AnyReader
from pathlib import Path

bag_path = sys.argv[1]
with AnyReader([Path(bag_path)]) as reader:
    duration = int(reader.duration / 1e9) - 5
print(duration)
