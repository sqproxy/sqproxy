import asyncio
import logging
from contextlib import suppress

import uvloop
from pid.decorator import pidfile

from . import config
from .epbf import run_ebpf_redirection
from .proxy import QueryProxy

logger = logging.getLogger('sqproxy')


@pidfile('sqproxy', piddir=config.settings.piddir)
def run():
    uvloop.install()
    with suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(_run_servers())


async def _run_servers():
    if not config.servers:
        logger.warning('No one server to run. Please check config')
        return

    proxies = []
    for name, server in config.servers:
        if server.entrypoint is None:
            entrypoint = QueryProxy
        else:
            entrypoint = server.entrypoint.obj

        proxy = entrypoint(server, name=name)
        proxies.append(proxy)

    futures = [asyncio.ensure_future(proxy.run()) for proxy in proxies]

    if config.ebpf and config.ebpf.enabled:
        logger.info('eBPF redirection enabled')
        logger.info('Wait all proxies to be ready ...')
        await asyncio.gather(*[proxy.wait_ready() for proxy in proxies],)
        logger.info('Wait all proxies to be ready ... Done!')
        futures.append(asyncio.ensure_future(run_ebpf_redirection()))
    else:
        logger.info('eBPF redirection disabled')

    await asyncio.gather(*futures)


if __name__ == '__main__':
    run()
