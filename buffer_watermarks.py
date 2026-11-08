import logging


class BufferWatermarkMonitor:
    """Log capacity alerts when a buffer crosses occupancy thresholds."""

    LEVELS = (
        (100, "FULL", logging.CRITICAL),
        (90, "CRITICAL", logging.ERROR),
        (75, "WARNING", logging.WARNING),
    )

    def __init__(self, buffer_name):
        self.buffer_name = buffer_name
        self.logger = logging.getLogger("chronosengine.buffer")
        self._last_level = "NORMAL"

    @staticmethod
    def status(unread, capacity):
        percentage = (unread / capacity) * 100

        if percentage >= 100:
            return "FULL"
        if percentage >= 90:
            return "CRITICAL"
        if percentage >= 75:
            return "WARNING"
        return "NORMAL"

    def update(self, unread, capacity):
        percentage = (unread / capacity) * 100
        current_level = self.status(unread, capacity)

        if current_level != self._last_level:
            level_order = {
                "NORMAL": 0,
                "WARNING": 1,
                "CRITICAL": 2,
                "FULL": 3,
            }

            if level_order[current_level] > level_order[self._last_level]:
                severity = next(
                    log_level
                    for threshold, name, log_level in self.LEVELS
                    if name == current_level
                )

                self.logger.log(
                    severity,
                    "%s buffer capacity %s: %.1f%% occupied "
                    "(%d/%d records); consumer lag is %d records",
                    self.buffer_name,
                    current_level,
                    percentage,
                    unread,
                    capacity,
                    unread,
                )

        self._last_level = current_level

        return {
            "watermark": current_level,
            "consumer_lag": unread,
            "consumer_lag_percent": round(percentage, 2),
        }
