import logging.config
import logging.handlers
import os


class BetterRotatingFileHandler(logging.handlers.RotatingFileHandler):
    def _open(self):
        os.makedirs(os.path.dirname(self.baseFilename), exist_ok=True)
        return super()._open()


def get_file_handler_opts(filename: str, level: str):
    return {
        'class': BetterRotatingFileHandler.__module__ + '.' + BetterRotatingFileHandler.__qualname__,
        'maxBytes': 1024 * 1024,
        'backupCount': 3,
        'level': level,
        'formatter': 'verbose',
        'filename': filename,
    }


def setup_logging(debug_filename: str = None, error_filename: str = None):
    if debug_filename is None:
        debug_filename = '/dev/null'

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
                    'level': 'DEBUG',
                    'formatter': 'verbose',
                },
                'debug_file': get_file_handler_opts(debug_filename, 'DEBUG'),
                'error_file': get_file_handler_opts(error_filename, 'ERROR'),
            },
            'loggers': {
                '': {'handlers': ['console', 'debug_file', 'error_file'], 'level': 'DEBUG', 'propagate': False},
                'PidFile': {'handlers': ['null'], 'propagate': False},
            },
        }
    )
    # fmt: on
