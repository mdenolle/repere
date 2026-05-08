"""STA/LTA golden suite for FrugalMind."""

from . import items, scorers
from .items import (
    ALL_SUITES,
    STALTAFetchCodeSuite,
    STALTAIntentExtractionSuite,
    STALTAPlotSuite,
    STALTAReportSuite,
    STALTATriggerCodeSuite,
)

__all__ = [
    "ALL_SUITES",
    "STALTAFetchCodeSuite",
    "STALTAIntentExtractionSuite",
    "STALTAPlotSuite",
    "STALTAReportSuite",
    "STALTATriggerCodeSuite",
    "items",
    "scorers",
]
