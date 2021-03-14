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
        for ifaddr, _prefix in addresses:
            if ip_address(ifaddr) == addr:
                return ipdb.by_index[idx]['ifname']
    return None


def get_ebpf_program_run_args():  # noqa: C901
    args = []

    is_wide = False
    interface = None
    for _server_name, server in config.settings.servers:
        bind_ip = server.network.bind_ip

        if str(bind_ip) == '0.0.0.0':
            server_interface = None
            is_wide = True
        else:
            server_interface = _get_addr_interface(bind_ip)
            if server_interface is None:
                raise AssertionError(f"Can't get interface name for {bind_ip}")

        if interface is None:
            interface = server_interface

        if server_interface != interface:
            raise config.ConfigurationError(
                'Different interfaces dont supported yet: ' f'{server_interface} != {interface}'
            )

        server_port = server.network.server_port
        bind_port = server.network.bind_port

        if not server.network.ebpf_no_redirect:
            if is_wide:
                arg = f'{server_port}:{bind_port}'
            else:
                arg = f'{bind_ip}:{server_port}:{bind_port}'

            args += ['-p', arg]

    if is_wide:
        logger.warning("Wide interface is not supported yet. '0.0.0.0' will be interpreted like 'default interface'")

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
