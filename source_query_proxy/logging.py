import logging.config
import logging.handlers
import os


class BetterRotatingFileHandler(logging.handlers.RotatingFileHandler):
    def _open(self):
        os.makedirs(os.path.dirname(self.baseFilename), exist_ok=True)
        return super()._open()


def setup_logging(filename=None):
    if filename is None:
        filename = '/dev/null'

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
                'file': {
                    'class': BetterRotatingFileHandler.__module__ + '.' + BetterRotatingFileHandler.__qualname__,
                    'maxBytes': 1024 * 1024,
                    'backupCount': 3,
                    'level': 'DEBUG',
                    'formatter': 'verbose',
                    'filename': filename,
                },
            },
            'loggers': {
                '': {'handlers': ['console', 'file'], 'level': 'DEBUG', 'propagate': False},
                'PidFile': {'handlers': ['null'], 'propagate': False},
            },
        }
    )
    # fmt: on
