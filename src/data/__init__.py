"""Data access modules. Public telemetry and synthetic readings stay separate."""

from .synthetic_sensors import AnomalyEvent, generate_sensor_data

__all__ = ["AnomalyEvent", "generate_sensor_data"]
