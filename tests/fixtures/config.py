import contextlib
import pathlib
import tempfile

import pytest
import yaml


@pytest.fixture(params=['192.168.1.1'])
def global_server_ip(request):
    return request.param


@pytest.fixture(params=['192.168.1.1'])
def global_bind_ip(request):
    return request.param


@pytest.fixture(params=[27015])
def dummy1_server_port(request):
    return request.param


@pytest.fixture(params=[27815])
def dummy1_bind_port(request):
    return request.param


@pytest.fixture()
def conf_d_globals(config_manager, global_server_ip, global_bind_ip):
    data = {
        'defaults': {
            '__global__': True,
            'a2s_info_cache_lifetime': 5,
            'src_query_port_lifetime': 10,
        },
        'servers': {},
        'ebpf': {'enabled': False},
    }

    network = []
    if global_server_ip:
        network.append(('server_ip', global_server_ip))

    if global_bind_ip:
        network.append(('bind_ip', global_bind_ip))

    if network:
        data['defaults']['network'] = dict(network)

    config_manager.set_default_globals(yaml.dump(data))

    return data


@pytest.fixture()
def _old_style_conf_d_globals(config_manager, conf_d_globals):
    global_val = conf_d_globals['defaults'].pop('__global__', None)
    prev_defaults = conf_d_globals['defaults']

    conf_d_globals['defaults'] = {
        'values': prev_defaults,
    }
    if global_val is not None:
        conf_d_globals['defaults']['global'] = global_val

    config_manager.default_globals.unlink()
    config_manager.set_default_globals(yaml.dump(conf_d_globals))


@pytest.fixture()
def conf_d_dummy_game1(config_manager, dummy1_bind_port, dummy1_server_port):
    data = {
        'defaults': {
            'network': {
                # place bind_port here to check local defaults
                'bind_port': dummy1_bind_port,
            },
        },
        'servers': {
            'DummyGame1': {
                'network': {
                    'server_port': dummy1_server_port,
                },
            },
        },
    }

    config_manager.add_config('01-dummy-game.yaml', yaml.dump(data))

    return data


@pytest.fixture()
def conf_d_dummy_game2(config_manager):
    data = {
        'servers': {
            'DummyGame2': {
                'network': {
                    'server_port': 27016,
                },
            },
        },
    }

    config_manager.add_config('02-dummy-game.yaml', yaml.dump(data))

    return data


class ConfigManager:
    def __init__(self, directory: pathlib.Path):
        self.directory = directory

    @property
    def default_globals(self):
        return self.directory.joinpath('00-globals.yaml')

    def add_config(self, name: str, content: str):
        assert name.endswith('.yaml')
        self.directory.joinpath(name).write_text(content)

    def set_default_globals(self, content):
        """Safe way to set global defaults settings"""
        if self.default_globals.exists():
            raise RuntimeError('Twice setting global defaults detected')
        self.default_globals.write_text(content)

    @contextlib.contextmanager
    def setup(self):
        from source_query_proxy import config

        mp: pytest.MonkeyPatch
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv('SQPROXY_DEBUG_LOG_ENABLED', 'false')
            mp.setenv('SQPROXY_CONFDIR_0', self.directory.as_posix())
            mp.setenv('SQPROXY_CONFDIR_1', 'unknown')

            old_settings = config.settings
            config.setup(reread=True)
            yield config

            # Touch lazy props
            # ensure parsing is correct
            # make it afterwards to allow make pre-parsing actions
            _ = config.ebpf
            _ = config.servers

            config.setup(old_settings)


@pytest.fixture()
def config_manager() -> ConfigManager:
    with tempfile.TemporaryDirectory() as directory:
        yield ConfigManager(pathlib.Path(directory))


@pytest.fixture()
def config(config_manager, conf_d_globals, conf_d_dummy_game1, conf_d_dummy_game2):
    with config_manager.setup() as new_config:
        yield new_config
