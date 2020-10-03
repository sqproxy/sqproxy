import asyncio
import logging
import os
from ipaddress import IPv4Address
from ipaddress import ip_address

import pyroute2

from . import config

logger = logging.getLogger(__name__)


def _get_addr_interface(addr: IPv4Address):
    ipdb = pyroute2.IPDB()
    for idx, addresses in ipdb.ipaddr.items():
        for ifaddr, prefix in addresses:
            if ip_address(ifaddr) == addr:
                return ipdb.by_index[idx]['ifname']
    return None


def get_ebpf_program_run_args():
    args = []

    wide_interface_warned = False
    interface = None
    for server_name, server in config.servers:
        if str(server.network.bind_ip) == '0.0.0.0':
            server_interface = None
            if not wide_interface_warned:
                logger.warning(
                    "Wide interface is not supported yet. '0.0.0.0' will be interpreted like 'default interface'"
                )
                wide_interface_warned = True
        else:
            server_interface = _get_addr_interface(server.network.bind_ip)
            assert server_interface is not None, f"Can't get interface name for {server.network.bind_ip}"

        if interface is None:
            interface = server_interface

        if server_interface != interface:
            raise config.ConfigurationError(
                'Different interfaces dont supported yet: ' f'{server_interface} != {interface}'
            )

        if not server.network.ebpf_no_redirect:
            args += ['-p', f'{server.network.server_port}:{server.network.bind_port}']

    if interface is not None:
        args += ['-i', interface]

    return args


async def run_ebpf_redirection():
    executable = config.ebpf.executable
    if not isinstance(executable, list):
        executable = [executable]

    cwd = None
    args = []

    if config.ebpf.script_path is not None:
        args.append(config.ebpf.script_path.name)
        cwd = config.ebpf.script_path.parent.as_posix()

    args += get_ebpf_program_run_args()

    logger.info('Run %s', executable + args)

    process = await asyncio.create_subprocess_exec(*executable, *args, stdout=asyncio.subprocess.PIPE, cwd=cwd)

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
