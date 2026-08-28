"""Unit conversion rules used by paper-summarizer."""

def convert(value, unit_from):
    if unit_from.lower() == "gpu":
        return value * 3.349e-7
    if unit_from.lower() == "barrer":
        return value * 3.346e-13
    return None
