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

    coros = []
    for name, server in config.servers:
        # TODO: import QueryProxy implementation and use it
        coros.append(QueryProxy(server, name=name).run())

    if config.ebpf and config.ebpf.enabled:
        logger.info('eBPF redirection enabled')
        coros.append(run_ebpf_redirection())
    else:
        logger.info('eBPF redirection disabled')

    await asyncio.gather(*coros)


if __name__ == '__main__':
    run()
