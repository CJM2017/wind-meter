from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from cape_ride.config import WindCredentials, load_config
from cape_ride.errors import ConfigurationError


class ConfigTests(unittest.TestCase):
    def test_loads_all_spots_and_supported_profiles(self) -> None:
        config = load_config()

        self.assertEqual(
            [332, 334, 330, 336],
            [item.provider_spot_id for item in config.spots.values()],
        )
        self.assertEqual(
            [
                "wall:tt",
                "wall:foil",
                "pond:tt",
                "pond:foil",
                "slick:tt",
                "flats:tt",
            ],
            list(config.profiles),
        )
        self.assertNotIn("slick:foil", config.profiles)
        self.assertNotIn("flats:foil", config.profiles)

    def test_credentials_require_both_secret_environment_values(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigurationError):
                WindCredentials.from_environment()

    def test_credentials_do_not_store_device_identity(self) -> None:
        with patch.dict(
            os.environ,
            {"IKITESURF_API_KEY": "key", "IKITESURF_TOKEN": "token"},
            clear=True,
        ):
            credentials = WindCredentials.from_environment()

        self.assertEqual("key", credentials.api_key)
        self.assertEqual("token", credentials.token)
        self.assertIn("iKitesurf", credentials.user_agent)


if __name__ == "__main__":
    unittest.main()
