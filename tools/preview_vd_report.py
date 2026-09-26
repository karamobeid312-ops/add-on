# -*- coding: utf-8 -*-
"""Voltage drop report of the sample cables (sample_vd.py), no Revit needed.

    python tools/preview_vd_report.py report.xlsx
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "VoltageDrop.extension", "lib"))
sys.path.insert(0, HERE)

from sample_vd import feeders  # noqa: E402
from vdrop.calc import Settings, calculate  # noqa: E402
from vdrop.report import ReportInfo, build, headline  # noqa: E402


def main(path):
    settings = Settings()
    result = calculate(feeders(), settings)
    info = ReportInfo(project="SAMPLE PROJECT", location="ABU DHABI, UAE", issue="Tender")
    build(result, settings, info).save(path)
    print(headline(result))
    print("Saved %s" % path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "voltage_drop_preview.xlsx")
