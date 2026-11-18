"""Parse plans from Planner replies."""

import re


def extract_plan(text):
    match = re.search(r"<plan>(.*?)</plan>", text, flags=re.DOTALL | re.IGNORECASE)
    return (match.group(1) if match else text).strip()
