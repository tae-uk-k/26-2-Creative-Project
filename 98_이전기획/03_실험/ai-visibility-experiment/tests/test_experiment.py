import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "experiment.py"
SPEC = importlib.util.spec_from_file_location("hanoon_experiment", MODULE_PATH)
experiment = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(experiment)


class ExperimentTests(unittest.TestCase):
    def test_inputs_have_expected_shape(self):
        prompts, restaurants = experiment.validate_inputs()
        self.assertEqual(12, len(prompts))
        self.assertEqual(30, len(restaurants))

    def test_manifest_has_240_unique_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "manifest.csv"
            count = experiment.build_manifest(output)
            self.assertEqual(240, count)
            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(240, len(rows))
            self.assertEqual(240, len({row["run_id"] for row in rows}))
            self.assertEqual(set(range(1, 241)), {int(row["random_order"]) for row in rows})

    def test_pilot_manifest_has_48_unique_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "pilot_manifest.csv"
            count = experiment.build_manifest(output, repeats=1, phase_code="P1")
            self.assertEqual(48, count)
            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(48, len(rows))
            self.assertEqual(48, len({row["run_id"] for row in rows}))
            self.assertTrue(all(row["run_id"].startswith("HANOON-P1-") for row in rows))

    def test_find_prompt_returns_scenario_variant(self):
        prompt = experiment.find_prompt("MD01", "pre_trip_us")
        self.assertIn("planning a trip", prompt["pre_trip_us"])
        self.assertIn("in Myeongdong now", prompt["in_korea"])

    def test_credit_guard_rejects_enabled_overage(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / "settings.json"
            settings.write_text('{"useG1Credits": true}', encoding="utf-8")
            with self.assertRaises(ValueError):
                experiment.ensure_ai_credit_overage_is_off(settings)

    def test_credit_guard_accepts_default_off(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / "settings.json"
            settings.write_text('{}', encoding="utf-8")
            experiment.ensure_ai_credit_overage_is_off(settings)

    def test_alias_matching_normalizes_punctuation_and_case(self):
        restaurant = {
            "canonical_name_en": "Q's Dakgangjeong",
            "name_ko": "큐스닭강정",
            "aliases": "Qs Dakgangjeong|Q's Fried Chicken",
        }
        response = experiment.normalize_entity("Try Qs DAKGANGJEONG in the market.")
        self.assertTrue(
            any(alias in response for alias in experiment.restaurant_aliases(restaurant))
        )


if __name__ == "__main__":
    unittest.main()
