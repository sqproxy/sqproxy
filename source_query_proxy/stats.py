# encoding: utf-8

import time


class IntervalCounter:
    def __init__(self, interval=1):
        self.interval = interval

        self._prev_count = 0
        self._current_count = 0

        self.marker = 0

    def _update(self, marker=None):
        if marker is None:
            marker = int(time.perf_counter())

        if marker - self.interval >= self.marker:
            self._prev_count = self._current_count
            self._current_count = 0
            self.marker = marker

    @property
    def count(self):
        self._update()
        return self._prev_count

    def emit(self):
        self._update()
        self._current_count += 1


class CSGOAggregator:
    def __init__(self):
        self.mps_counter = IntervalCounter()

    def aggregate(self, addr, msg=None):
        self.mps_counter.emit()

    def format_lines(self):
        lines = [
            'Messages per second: {mps} m/s'.format(mps=self.mps_counter.count),
        ]

        return lines

    def format_stats(self):
        return '\n'.join(self.format_lines())


def test():
    counter = IntervalCounter(interval=5)

    for _ in range(10000):
        counter.emit()
        time.sleep(0.1)

        print('Counter:', counter.count, end='\r')  # noqa: ignore=T001


if __name__ == '__main__':
    test()
