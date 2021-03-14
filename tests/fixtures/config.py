import os
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
def conf_d_globals(global_server_ip, global_bind_ip):
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

    return yaml.dump(data)


@pytest.fixture(params=[None])
def conf_d_dummy_game1(request, dummy1_bind_port, dummy1_server_port):
    if request.param is not None:
        return request.param

    return yaml.dump(
        {
            'defaults': {},
            'servers': {
                'DummyGame1': {
                    'network': {
                        'server_port': dummy1_server_port,
                        'bind_port': dummy1_bind_port,
                    },
                },
            },
        }
    )


@pytest.fixture(params=[None])
def conf_d_dummy_game2(request):
    if request.param is not None:
        return request.param

    return yaml.dump(
        {
            'servers': {
                'DummyGame2': {
                    'network': {
                        'server_port': 27016,
                    },
                },
            },
        }
    )


@pytest.fixture()
def config(conf_d_globals, conf_d_dummy_game1, conf_d_dummy_game2):
    from source_query_proxy import config

    with tempfile.TemporaryDirectory() as directory:
        directory = pathlib.Path(directory)
        directory.joinpath('00-globals.yaml').write_text(conf_d_globals)
        if conf_d_dummy_game1:
            directory.joinpath('01-dummy-game.yaml').write_text(conf_d_dummy_game1)
        if conf_d_dummy_game2:
            directory.joinpath('02-dummy-game.yaml').write_text(conf_d_dummy_game2)
        os.environ['SQPROXY_DEBUG_LOG_ENABLED'] = 'false'
        os.environ['SQPROXY_CONFDIR_0'] = directory.as_posix()
        os.environ['SQPROXY_CONFDIR_1'] = 'unknown'
        config.setup(reread=True)

        yield config

        # Touch lazy props
        # ensure parsing is correct
        # make it afterwards to allow make pre-parsing actions
        _ = config.ebpf
        _ = config.servers
