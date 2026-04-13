import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add src to sys.path to allow relative package testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Import package modules to test
from TermRad import weather_api
from TermRad import radar_animator
from TermRad import app as TermRad


class TestTermRadIntegrated(unittest.TestCase):
    # --- SETUP ---
    def setUp(self):
        # Clear lru_caches before each test to ensure fresh results
        weather_api.fetch_json.cache_clear()
        weather_api.get_coords_auto.cache_clear()
        weather_api.get_point_metadata.cache_clear()
        weather_api.get_alerts.cache_clear()
        weather_api.get_forecast.cache_clear()
        weather_api.get_numerical_forecast.cache_clear()
        TermRad.get_settings.cache_clear()

    # --- API TESTS (weather_api.py) ---
    @patch("TermRad.weather_api.fetch_json")
    def test_api_get_coords_manual_zip(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "lat": "43.0246800",
                "lon": "-83.5267848",
                "display_name": "Davison, Michigan, 48423, USA",
            }
        ]
        lat, lon, country = weather_api.get_coords_manual("48423")
        self.assertEqual(lat, "43.0246800")
        self.assertEqual(country, "USA")
        # Ensure it appends USA for zip codes
        self.assertIn("q=48423, USA", mock_fetch.call_args[0][0])

    @patch("TermRad.weather_api.fetch_json")
    def test_api_nws_error_handling(self, mock_fetch):
        mock_fetch.return_value = None
        forecast = weather_api.get_numerical_forecast("0", "0")
        self.assertEqual(forecast, [])

    # --- RADAR TESTS (radar_animator.py) ---
    def test_radar_latlon_to_pixel_mapping(self):
        width, height = 100, 100
        # MICHIGAN_BBOX = "-87.6643,41.69,-81.2357,45.80" (current calibrated)

        # Test SW Corner (41.69, -87.6643) -> Should be (0, 99)
        x, y = radar_animator.latlon_to_pixel(
            41.69, -87.6643, radar_animator.MICHIGAN_BBOX, width, height
        )
        self.assertEqual(x, 0)
        self.assertEqual(y, 99)

        # Test Out of Bounds
        result = radar_animator.latlon_to_pixel(
            34.05, -118.24, radar_animator.MICHIGAN_BBOX, width, height
        )
        self.assertIsNone(result)

    # --- APP LOGIC TESTS (TermRad.py helpers) ---
    def test_logic_get_temp_color(self):
        # Cold (Blue)
        self.assertEqual(TermRad.get_temp_color(20), "#5555FF")
        # Mild (Yellow)
        self.assertEqual(TermRad.get_temp_color(55), "#FFFF55")
        # Warm (Orange)
        self.assertEqual(TermRad.get_temp_color(75), "#FFAA00")
        # Hot (Red)
        self.assertEqual(TermRad.get_temp_color(95), "#FF5555")

    @patch("TermRad.app.get_settings")
    def test_logic_get_time_format(self, mock_settings):
        # 12-hour (Default)
        mock_settings.return_value = {"time_format": "12 hour"}
        self.assertIn("%I:%M %p", TermRad.get_time_format())

        # 24-hour
        TermRad.get_settings.cache_clear()
        mock_settings.return_value = {"time_format": "24 hour"}
        self.assertEqual(TermRad.get_time_format(), "%H:%M:%S")

    def test_logic_convert_temp(self):
        # 32F -> 0C
        self.assertEqual(TermRad.convert_temp(32, "C"), 0)
        # 212F -> 100C
        self.assertEqual(TermRad.convert_temp(212, "C"), 100)
        # 75F -> 75F
        self.assertEqual(TermRad.convert_temp(75, "F"), 75)

    @patch("TermRad.app.get_settings")
    def test_logic_get_temperature_unit(self, mock_settings):
        mock_settings.return_value = {"temperature": "Celsius"}
        self.assertEqual(TermRad.get_temperature_unit(), "C")

        TermRad.get_settings.cache_clear()
        mock_settings.return_value = {"temperature": "Fahrenheit"}
        self.assertEqual(TermRad.get_temperature_unit(), "F")

    @patch("TermRad.app.get_settings")
    @patch("TermRad.app.get_coords_auto")
    @patch("TermRad.app.get_coords_manual")
    def test_logic_get_app_coordinates(self, mock_manual, mock_auto, mock_settings):
        # Test Use IP
        mock_settings.return_value = {"use_ip": True}
        mock_auto.return_value = ("1", "2", "US")
        TermRad.get_app_coordinates()
        mock_auto.assert_called_once()

        # Test Zip Code
        TermRad.get_settings.cache_clear()
        mock_settings.return_value = {"use_ip": False, "zip_code": "48423"}
        mock_manual.return_value = ("3", "4", "US")
        TermRad.get_app_coordinates()
        mock_manual.assert_called_with("48423")

    # --- SETTINGS IO TESTS ---
    @patch("builtins.open", new_callable=MagicMock)
    @patch("json.dump")
    @patch("TermRad.app.get_settings")
    def test_settings_save_and_load(self, mock_get, mock_json_dump, mock_open):
        test_settings = {"test": "value", "use_ip": True}

        # Test saving (mocking open and json.dump)
        TermRad.save_settings(test_settings)
        mock_json_dump.assert_called_once()

        # Test loading logic via helper
        mock_get.return_value = test_settings
        loaded = TermRad.get_settings()
        self.assertEqual(loaded["test"], "value")


    # --- ASSET LOADING TESTS ---
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_logic_load_asset_missing(self, mock_open):
        # Should return empty string if file missing
        self.assertEqual(TermRad.load_asset("nonexistent.txt"), "")

    # --- NETWORK ROBUSTNESS TESTS ---
    @patch('TermRad.weather_api.requests.get')
    @patch('TermRad.weather_api.time.sleep') # Don't actually wait during tests
    def test_api_fetch_json_retry_logic(self, mock_sleep, mock_get):
        # Simulate 2 failures followed by 1 success
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 500
        
        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {"key": "value"}
        
        mock_get.side_effect = [mock_response_fail, mock_response_fail, mock_response_success]
        
        result = weather_api.fetch_json("http://test.com", "Test API")
        
        self.assertEqual(result, {"key": "value"})
        self.assertEqual(mock_get.call_count, 3) # Verified it retried exactly as intended

if __name__ == "__main__":
    unittest.main()
