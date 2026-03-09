import unittest

from weather_compare_bot import _allergy_level, _fallback_summary, build_weather_payload


class WeatherCompareBotTests(unittest.TestCase):
    def test_allergy_level_low(self) -> None:
        hourly = {"grass_pollen": [0, 3, 10], "birch_pollen": [2, 4]}
        self.assertEqual(_allergy_level(hourly), "Low")

    def test_allergy_level_medium(self) -> None:
        hourly = {"grass_pollen": [5, 40, 18]}
        self.assertEqual(_allergy_level(hourly), "Medium")

    def test_allergy_level_high(self) -> None:
        hourly = {"ragweed_pollen": [85]}
        self.assertEqual(_allergy_level(hourly), "High")

    def test_fallback_summary_mentions_better_city(self) -> None:
        city1 = {
            "city": "Toronto",
            "current": {
                "real_feel_c": 18,
                "uv_index": 4,
                "rain_probability_pct": 10,
                "visibility_m": 10000,
                "weather_label": "partly cloudy",
                "fog_risk": False,
                "allergy_index": "Low",
            },
        }
        city2 = {
            "city": "Vancouver",
            "current": {
                "real_feel_c": 13,
                "uv_index": 7,
                "rain_probability_pct": 65,
                "visibility_m": 800,
                "weather_label": "fog",
                "fog_risk": True,
                "allergy_index": "High",
            },
        }
        payload = build_weather_payload(city1, city2)
        summary = _fallback_summary(payload)

        self.assertIn("Toronto", summary)
        self.assertIn("Vancouver", summary)


if __name__ == "__main__":
    unittest.main()
