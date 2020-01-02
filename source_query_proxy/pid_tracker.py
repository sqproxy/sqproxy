# encoding: utf-8

import os
import re

from contextlib import suppress, contextmanager


class PIDTracker:
    _rbtime=re.compile(r'^btime (\d+)$', flags=re.MULTILINE)

    def __init__(self, pid_fpath):
        self.pid_fpath = pid_fpath
        self.btime = self.get_last_boot_timestamp()

    @classmethod
    def from_file_path(cls, file_path):
        exec_filename = os.path.basename(file_path)
        exec_dir = os.path.dirname(os.path.abspath(file_path))

        pid_fpath = os.path.join(exec_dir, exec_filename)

        return cls(pid_fpath)

    def get_last_boot_timestamp(self):
        with open('/proc/stat') as fstream:
            mo = self._rbtime.search(fstream.read())

        return mo and mo.group(1) or None

    def is_exists(self, pid):
        try:
            os.listdir('/proc/%s/' % pid)
        except FileNotFoundError:
            return False

        return True

    def is_running(self):
        if not os.path.exists(self.pid_fpath):
            return False

        with open(self.pid_fpath) as fstream:
            pid, btime = fstream.read().split(':')

        return self.is_exists(pid) and self.btime == btime

    def write_state(self):
        with open(self.pid_fpath, 'w') as fstream:
            fstream.write(':'.join((str(os.getpid()), self.btime)))

    def cleanup_state(self):
        with suppress(FileNotFoundError):
            os.remove(self.pid_fpath)

    @contextmanager
    def track(self):
        self.write_state()
        try:
            yield
        finally:
            self.cleanup_state()


def main():
    pid_fpath = 'PIDTracker.test.pid'
    ptrack = PIDTracker(pid_fpath)

    if ptrack.is_running():
        return

    with ptrack.track():
        print(
            "{pid_fpath} now created/overwrited\n"
            "and will be removed after this text printed!".format(
                pid_fpath=pid_fpath,
            )
        )


if __name__ == '__main__':
    main()
