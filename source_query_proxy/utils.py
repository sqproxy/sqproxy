import contextlib
import socket


def get_available_port():
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def is_port_available(port: int):
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        try:
            s.bind(('', port))
        except OverflowError:
            return False
        except OSError as exc:
            if 'Address already in use' in str(exc):
                return False
            raise

    return True
