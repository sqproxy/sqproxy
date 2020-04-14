import os
import pathlib
import tempfile

import pytest

from source_query_proxy import config


@pytest.fixture()
def conf_d_globals():
    return '''
defaults:
  global: True
  values:
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
  MyVeryBigServer:
    network:
      server_port: 27016
      bind_port: 27816
'''


@pytest.fixture()
def _dummy_config(conf_d_globals, conf_d_dummy_game):
    with tempfile.TemporaryDirectory() as directory:
        directory = pathlib.Path(directory)
        directory.joinpath('00-globals.yaml').write_text(conf_d_globals)
        directory.joinpath('01-dummy-game.yaml').write_text(conf_d_dummy_game)
        os.environ['SQPROXY_DEBUG_LOG_ENABLED'] = 'false'
        os.environ['SQPROXY_CONFDIR_0'] = directory.as_posix()
        os.environ['SQPROXY_CONFDIR_1'] = 'unknown'
        config.setup()
        yield


def test_global_defaults_injected(_dummy_config):
    assert config.settings.get_merged_config_data()['servers'] == {
        'MyLittleServer': {
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
def test_ebpf_cant_be_configured_twice(_dummy_config, conf_d_dummy_game):
    assert config.settings.merged_config_data['ebpf'] == {'enabled': False}
