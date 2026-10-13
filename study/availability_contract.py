"""Nominal-hour arrival and learner-use contract; not a fitting runner."""
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class AvailabilityContract:
    observation_delay_hours: int = 0
    training_use_delay_hours: int = 0
    horizon_hours: int = 6
    completion_hours: int = 1

    def __post_init__(self):
        for name in ("observation_delay_hours", "training_use_delay_hours",
                     "horizon_hours", "completion_hours"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.horizon_hours == 0 or self.completion_hours == 0:
            raise ValueError("horizon and completion must be positive")

    def measurement_arrival(self, observation_hour: datetime) -> datetime:
        return observation_hour + timedelta(
            hours=self.completion_hours + self.observation_delay_hours)

    def latest_feature_hour(self, forecast_origin: datetime) -> datetime:
        return forecast_origin - timedelta(
            hours=self.completion_hours + self.observation_delay_hours)

    def label_usable_at(self, forecast_origin: datetime) -> datetime:
        target_hour = forecast_origin + timedelta(hours=self.horizon_hours)
        return self.measurement_arrival(target_hour) + timedelta(
            hours=self.training_use_delay_hours)

    def can_use_label(self, forecast_origin: datetime, cutoff: datetime) -> bool:
        return self.label_usable_at(forecast_origin) <= cutoff
