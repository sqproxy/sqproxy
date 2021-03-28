import pathlib
from unittest.mock import ANY
from unittest.mock import call
from unittest.mock import create_autospec

import pytest

from source_query_proxy import config as sqproxy_config
from source_query_proxy import utils


@pytest.fixture(params=['current', 'old'], autouse=True)
def config_mode(request):
    if request.param is None:
        # noop: allow ignore this fixture due: https://github.com/pytest-dev/pytest/issues/4666
        return None

    if request.param == 'current':
        return request.getfixturevalue('conf_d_globals')
    else:
        assert request.param == 'old'
        return request.getfixturevalue('_old_style_conf_d_globals')


@pytest.mark.parametrize('config_mode', [None], indirect=True)
def test_config_files_iterated_in_ascending_order(config_mode):
    """listdir return paths in arbitrary order, we need expected order"""

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

    assert [f.name for f in sqproxy_config.iter_config_files(fake_dir)] == [
        '01.yaml',
        '10.yaml',
        'arbitrary.yaml',
    ]


def test_global_defaults_injected(config):
    assert config.settings.merged_config_data['servers'] == {
        'DummyGame1': {
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
        'DummyGame2': {
            'meta': ANY,
            'network': {
                'server_ip': '192.168.1.1',
                'bind_ip': '192.168.1.1',
                'server_port': 27016,
            },
            'a2s_info_cache_lifetime': 5,
            'src_query_port_lifetime': 10,
        },
    }


def test_ebpf_cant_be_configured_twice(config_manager, conf_d_globals):
    config_manager.add_config(
        '01-redefine-ebpf-block.yaml',
        '''
ebpf:
  enabled: True
''',
    )
    with pytest.raises(sqproxy_config.ConfigurationError), config_manager.setup():
        ...


@pytest.mark.parametrize('global_bind_ip', [None], indirect=True, ids=['no-global-bind-ip'])
def test_bind_ip_same_as_server_ip(config, global_bind_ip, global_server_ip):
    for _, server in config.settings.servers:
        assert str(server.network.bind_ip) == global_server_ip


@pytest.mark.parametrize('dummy1_bind_port', [None, 0], ids=['null', 'zero'])
def test_missing_bind_port_chosen_automatically_pretty(config, dummy1_bind_port, mocker):
    is_port_available_mock = mocker.patch.object(utils, 'is_port_available', return_value=True)
    assert config.settings.servers[0][1].network.bind_port == 27815
    assert call(27815) in is_port_available_mock.call_args_list


@pytest.mark.parametrize('dummy1_bind_port', [None, 0], ids=['null', 'zero'])
def test_missing_bind_port_chosen_automatically_random(config, dummy1_bind_port, mocker):
    is_port_available_mock = mocker.patch.object(utils, 'is_port_available', return_value=False)
    get_available_port_mock = mocker.patch.object(utils, 'get_available_port', return_value=8888)
    assert config.settings.servers[0][1].network.bind_port == 8888
    assert is_port_available_mock.called
    assert get_available_port_mock.called
