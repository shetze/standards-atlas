"""Semantic roles for clause-like domain objects."""

from __future__ import annotations

from enum import StrEnum


class SemanticRole(StrEnum):
    """Fine-grained semantic role of a clause-like item."""

    FOREWORD = "foreword"
    INTRODUCTION = "introduction"
    SCOPE = "scope"
    NORMATIVE_REFERENCES = "normative_references"
    TERMS_AND_DEFINITIONS = "terms_and_definitions"
    ABBREVIATIONS = "abbreviations"

    OBJECTIVES = "objectives"
    REQUIREMENTS = "requirements"
    RECOMMENDATIONS = "recommendations"
    INPUTS = "inputs"
    OUTPUTS = "outputs"
    WORK_PRODUCTS = "work_products"

    TABLE = "table"
    FIGURE = "figure"
    NOTE = "note"
    EXAMPLE = "example"
    ANNEX = "annex"
    BIBLIOGRAPHY = "bibliography"

    COMPLIANCE = "compliance"
    CONFORMANCE = "conformance"
