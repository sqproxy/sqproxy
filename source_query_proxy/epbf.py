import asyncio
import logging
import os
from ipaddress import IPv4Address
from ipaddress import ip_address

import pyroute2

from . import config

logger = logging.getLogger(__name__)


def _get_addr_interface(addr: IPv4Address, ipdb=pyroute2.IPDB()):
    for idx, addresses in ipdb.ipaddr.items():
        for ifaddr, prefix in addresses:
            if ip_address(ifaddr) == addr:
                return ipdb.by_index[idx]['ifname']
    return None


def get_ebpf_program_run_args():
    args = []

    interface = None
    for server_name, server in config.servers:
        server_interface = _get_addr_interface(server.network.bind_ip)
        assert server_interface is not None, f"Can't get interface name for {server.network.bind_ip}"

        if interface is None:
            interface = server_interface

        if server_interface != interface:
            raise config.ConfigurationError(
                'Different interfaces dont supported yet: ' f'{server_interface} != {interface}'
            )

        args += ['-p', f'{server.network.server_port}:{server.network.bind_port}']

    args += ['-i', interface]

    return args


async def run_ebpf_redirection():
    program = config.ebpf.executable

    args = [config.ebpf.script_path.name]
    args += get_ebpf_program_run_args()

    logger.info('Run %s %s', program, args)

    process = await asyncio.create_subprocess_exec(
        program, *args, stdout=asyncio.subprocess.PIPE, cwd=config.ebpf.script_path.parent.as_posix(),
    )

    while True:
        data = await process.stdout.readline()
        if data:
            logger.info(data.decode().rstrip())

        if process.stdout.at_eof():
            break

    retcode = process.returncode
    if retcode != os.EX_OK:
        logger.exception('eBPF redirection exit with code %s', retcode)
        raise RuntimeError

    logger.info('eBPF redirection normally exit with 0 code')
