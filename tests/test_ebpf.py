import functools
import uuid
from ipaddress import IPv4Address
from unittest.mock import ANY

import pytest

from source_query_proxy import epbf


def _fake_get_addr_interface(addr: IPv4Address, _known: dict):
    interface = _known.get(addr)
    if interface is None:
        interface = _known[addr] = str(uuid.uuid4())
    return interface


@pytest.fixture(autouse=True, params=[None], ids=['generate'])
def mock_get_addr_interface(request, mocker):
    """Interface name will be generated instead getting through pyroute2 lib

    You can parametrize this fixture by mapping: addr -> interface_name
    """
    known = {}
    if request.param is not None:
        known = request.param

    mocker.patch.object(
        epbf,
        '_get_addr_interface',
        side_effect=functools.partial(_fake_get_addr_interface, _known=known),
    )
    return known


def test_get_ebpf_program_run_args(config):
    assert epbf.get_ebpf_program_run_args() == [
        '-p',
        '192.168.1.1:27015:27815',
        '-p',
        '192.168.1.1:27016:27816',
        '-i',
        ANY,
    ]


@pytest.mark.parametrize('global_bind_ip', ['0.0.0.0'], ids=['wide'])
def test_get_ebpf_program_run_args_wide_interface(config, global_bind_ip):
    assert epbf.get_ebpf_program_run_args() == [
        '-p',
        '27015:27815',
        '-p',
        '27016:27816',
    ]
