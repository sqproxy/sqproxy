import os
import json


def apply_defaults(target, defaults):
    defaults_keys = set(defaults.keys())
    for key in defaults_keys.difference(target.keys()):
        target[key] = defaults[key]


def _load_config(filename, encoding='utf-8'):
    with open(filename, encoding=encoding) as fp:
        cfg = json.load(fp)

    global_defaults = cfg.pop('defaults', None)

    for section in cfg.values():
        section_defaults = section.pop('defaults', None)

        for server in section.values():
            if section_defaults is not None:
                apply_defaults(server, section_defaults)

            if global_defaults is not None:
                apply_defaults(server, global_defaults)

    return cfg


config = _load_config(
    os.path.join(
        os.path.dirname(__file__),
        'config.json',
    ),
)
