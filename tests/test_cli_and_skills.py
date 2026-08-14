from __future__ import annotations

import contextlib
import io
import os
import unittest
from argparse import ArgumentTypeError
from pathlib import Path
from unittest.mock import patch

from cape_ride.cli_support import forecast_days
from cape_ride.wind_cli import main as wind_main

ROOT = Path(__file__).parents[1]


class CliAndSkillTests(unittest.TestCase):
    def test_forecast_days_accepts_boundaries(self) -> None:
        self.assertEqual(1, forecast_days("1"))
        self.assertEqual(10, forecast_days("10"))

    def test_forecast_days_rejects_invalid_values(self) -> None:
        for value in ("0", "11", "three"):
            with self.subTest(value=value):
                with self.assertRaises(ArgumentTypeError):
                    forecast_days(value)

    def test_missing_credentials_fail_without_secret_output(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = wind_main(["current", "--spot", "wall"])

        self.assertEqual(1, exit_code)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("IKITESURF_API_KEY", stderr.getvalue())
        self.assertNotIn("wf_token=", stderr.getvalue())

    def test_three_openclaw_skills_have_required_frontmatter(self) -> None:
        names = ("ikitesurf-wind", "cape-tides", "cape-ride-check")
        for name in names:
            with self.subTest(name=name):
                text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                self.assertIn(f"name: {name}\n", text)
                self.assertIn("description:", text)


if __name__ == "__main__":
    unittest.main()
