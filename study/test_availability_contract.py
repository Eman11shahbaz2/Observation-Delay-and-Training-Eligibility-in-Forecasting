from datetime import datetime, timedelta
import unittest
from availability_contract import AvailabilityContract


class ContractChecks(unittest.TestCase):
    origin = datetime(2026, 1, 10, 12)

    def test_four_declared_settings(self):
        expected = {(0, 0): (1, 7), (0, 24): (1, 31),
                    (24, 0): (25, 31), (24, 24): (25, 55)}
        for (observation, training), (feature_age, maturity) in expected.items():
            c = AvailabilityContract(observation, training)
            self.assertEqual(c.latest_feature_hour(self.origin),
                             self.origin - timedelta(hours=feature_age))
            self.assertEqual(c.label_usable_at(self.origin),
                             self.origin + timedelta(hours=maturity))

    def test_training_restriction_does_not_change_arrival_or_features(self):
        a, b = AvailabilityContract(24, 0), AvailabilityContract(24, 24)
        self.assertEqual(a.measurement_arrival(self.origin), b.measurement_arrival(self.origin))
        self.assertEqual(a.latest_feature_hour(self.origin), b.latest_feature_hour(self.origin))
        self.assertEqual(b.label_usable_at(self.origin) - a.label_usable_at(self.origin),
                         timedelta(hours=24))

    def test_measurement_delay_affects_both_roles_consistently(self):
        c = AvailabilityContract(24, 0)
        target_hour = self.origin + timedelta(hours=6)
        self.assertEqual(c.label_usable_at(self.origin), c.measurement_arrival(target_hour))
        self.assertEqual(c.measurement_arrival(c.latest_feature_hour(self.origin)), self.origin)
        self.assertGreater(c.measurement_arrival(c.latest_feature_hour(self.origin)
                                                + timedelta(hours=1)), self.origin)

    def test_primary_pair_has_equal_maturity_for_many_origins(self):
        a, b = AvailabilityContract(24, 0), AvailabilityContract(0, 24)
        for hour in range(-200, 201):
            origin = self.origin + timedelta(hours=hour)
            self.assertEqual(a.label_usable_at(origin), b.label_usable_at(origin))
            self.assertNotEqual(a.latest_feature_hour(origin), b.latest_feature_hour(origin))

    def test_exact_maturity_boundary(self):
        c = AvailabilityContract(24, 24)
        boundary = c.label_usable_at(self.origin)
        self.assertFalse(c.can_use_label(self.origin, boundary - timedelta(seconds=1)))
        self.assertTrue(c.can_use_label(self.origin, boundary))

    def test_invalid_timing_settings_rejected(self):
        for kwargs in ({"observation_delay_hours": -1}, {"training_use_delay_hours": 0.5},
                       {"horizon_hours": 0}, {"completion_hours": 0},
                       {"training_use_delay_hours": True}):
            with self.assertRaises(ValueError):
                AvailabilityContract(**kwargs)


if __name__ == '__main__':
    unittest.main()
