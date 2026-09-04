"""Compare response-time stats JSON files between two stands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union


def compare_stands(file1: Union[str, Path], file2: Union[str, Path], label1: str = "a", label2: str = "b") -> str:
    """Print and return a table comparing min/avg/max timings per endpoint."""
    with open(file1, "r", encoding="utf-8") as f1, open(file2, "r", encoding="utf-8") as f2:
        stats1 = json.load(f1)
        stats2 = json.load(f2)

    lines = [
        f"{'Endpoint':<24} "
        f"{'Min('+label1+')':<12} {'Min('+label2+')':<12} {'Diff':<10} "
        f"{'Avg('+label1+')':<12} {'Avg('+label2+')':<12} {'Diff':<10} "
        f"{'Max('+label1+')':<12} {'Max('+label2+')':<12} {'Diff':<10}",
        "-" * 120,
    ]

    for endpoint in sorted(set(stats1.keys()) | set(stats2.keys())):
        s1 = stats1.get(endpoint, {"min_time": 0, "max_time": 0, "avg_time": 0})
        s2 = stats2.get(endpoint, {"min_time": 0, "max_time": 0, "avg_time": 0})
        min_diff = s1["min_time"] - s2["min_time"]
        avg_diff = s1["avg_time"] - s2["avg_time"]
        max_diff = s1["max_time"] - s2["max_time"]
        lines.append(
            f"{endpoint:<24} "
            f"{s1['min_time']:<12.3f} {s2['min_time']:<12.3f} {min_diff:<10.3f} "
            f"{s1['avg_time']:<12.3f} {s2['avg_time']:<12.3f} {avg_diff:<10.3f} "
            f"{s1['max_time']:<12.3f} {s2['max_time']:<12.3f} {max_diff:<10.3f}"
        )

    table = "\n".join(lines)
    print(table)
    return table
