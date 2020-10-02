import logging.config
import logging.handlers
import os
import sys


class BetterRotatingFileHandler(logging.handlers.RotatingFileHandler):
    def _open(self):
        os.makedirs(os.path.dirname(self.baseFilename), exist_ok=True)
        return super()._open()


def get_file_handler_opts(filename: str, level: str):
    if filename == '/dev/null':
        return {
            'class': 'logging.NullHandler',
            'level': level,
        }

    if filename.startswith('/dev/'):
        filename = filename.rstrip('/')
        stream = {'/dev/stderr': sys.stderr, '/dev/stdout': sys.stdout}[filename]
        return {
            'class': 'logging.StreamHandler',
            'stream': stream,
            'level': level,
            'formatter': 'verbose',
        }

    return {
        'class': BetterRotatingFileHandler.__module__ + '.' + BetterRotatingFileHandler.__qualname__,
        'maxBytes': 1024 * 1024,
        'backupCount': 3,
        'level': level,
        'formatter': 'verbose',
        'filename': filename,
    }


def setup_logging(loglevel=logging.INFO, error_filename: str = None):
    if error_filename is None:
        error_filename = '/dev/null'

    # fmt: off
    logging.config.dictConfig(
        {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'verbose': {
                    'format': '%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
                },
            },
            'handlers': {
                'null': {
                    'level': 'DEBUG',
                    'class': 'logging.NullHandler',
                },
                'console': {
                    'class': 'logging.StreamHandler',
                    'level': loglevel,
                    'formatter': 'verbose',
                },
                'error_file': get_file_handler_opts(error_filename, 'ERROR'),
            },
            'loggers': {
                '': {'handlers': ['console', 'error_file'], 'level': 'DEBUG', 'propagate': False},
                'PidFile': {'handlers': ['null'], 'propagate': False},
            },
        }
    )
    # fmt: on
