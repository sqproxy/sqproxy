import os
import pathlib
import tempfile
from unittest.mock import ANY
from unittest.mock import create_autospec

import pytest

from source_query_proxy import config


@pytest.fixture()
def conf_d_globals():
    return '''
defaults:
  __global__: True
  network:
    server_ip: '192.168.1.1'
    bind_ip: '192.168.1.1'
  a2s_info_cache_lifetime: 5
  src_query_port_lifetime: 10

# See 01-dummy-game.yaml
servers:

ebpf:
  enabled: False
    '''


@pytest.fixture(params=[None])
def conf_d_dummy_game(request):
    if request.param is not None:
        return request.param
    return '''
defaults:

servers:
  MyLittleServer:
    network:
      server_port: 27015
      bind_port: 27815
'''


@pytest.fixture()
def conf_d_dummy_game2():
    return '''
servers:
  MyVeryBigServer:
    network:
      server_port: 27016
      bind_port: 27816
'''


@pytest.fixture()
def _dummy_config(conf_d_globals, conf_d_dummy_game, conf_d_dummy_game2):
    with tempfile.TemporaryDirectory() as directory:
        directory = pathlib.Path(directory)
        directory.joinpath('00-globals.yaml').write_text(conf_d_globals)
        directory.joinpath('01-dummy-game.yaml').write_text(conf_d_dummy_game)
        directory.joinpath('02-dummy-game.yaml').write_text(conf_d_dummy_game2)
        os.environ['SQPROXY_DEBUG_LOG_ENABLED'] = 'false'
        os.environ['SQPROXY_CONFDIR_0'] = directory.as_posix()
        os.environ['SQPROXY_CONFDIR_1'] = 'unknown'
        config.setup(reread=True)

        # Touch lazy props
        # ensure parsing is correct
        _ = config.ebpf
        _ = config.servers
        yield


def test_config_files_iterated_in_ascending_order():
    """listdir return paths in arbitrary order, we need expected order
    """

    def make_fake_config_file(name):
        obj = create_autospec(pathlib.Path)
        obj.is_file.return_value = True
        obj.name = name
        obj.as_posix.return_value = f'/as/posix/{obj.name}'
        return obj

    arbitrary_ordered_files = [
        make_fake_config_file('10.yaml'),
        make_fake_config_file('arbitrary.yaml'),
        make_fake_config_file('01.yaml'),
    ]

    fake_dir = create_autospec(pathlib.Path)
    fake_dir.exists.return_value = True
    fake_dir.is_dir.return_value = True
    fake_dir.iterdir.side_effect = lambda: iter(arbitrary_ordered_files)

    assert [f.name for f in config.iter_config_files(fake_dir)] == [
        '01.yaml',
        '10.yaml',
        'arbitrary.yaml',
    ]


@pytest.mark.usefixtures('_dummy_config')
def test_global_defaults_injected():
    assert config.settings.get_merged_config_data()['servers'] == {
        'MyLittleServer': {
            'meta': ANY,
            'network': {
                'server_ip': '192.168.1.1',
                'bind_ip': '192.168.1.1',
                'server_port': 27015,
                'bind_port': 27815,
            },
            'a2s_info_cache_lifetime': 5,
            'src_query_port_lifetime': 10,
        },
        'MyVeryBigServer': {
            'meta': ANY,
            'network': {
                'server_ip': '192.168.1.1',
                'bind_ip': '192.168.1.1',
                'server_port': 27016,
                'bind_port': 27816,
            },
            'a2s_info_cache_lifetime': 5,
            'src_query_port_lifetime': 10,
        },
    }


@pytest.mark.parametrize(
    'conf_d_dummy_game',
    [
        '''
ebpf:
  enabled: True
'''
    ],
    indirect=True,
)
@pytest.mark.xfail(raises=config.ConfigurationError)
@pytest.mark.usefixtures('_dummy_config')
def test_ebpf_cant_be_configured_twice(conf_d_dummy_game):
    assert config.settings.get_merged_config_data()['ebpf'] == {'enabled': False}
