# encoding: utf-8

import os
import sys
import math
import random
import pathlib
import asyncio
import logging
import logging.handlers
import itertools

import pylru

import stats
import source.messages

from pid_tracker import PIDTracker


PY_35 = sys.version_info >= (3, 5)


try:
    import uvloop
except ImportError:
    uvloop = None


__version__ = '0.15.0'


logdir = pathlib.Path(__file__).parent / 'logs'
os.makedirs(str(logdir), exist_ok=True)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

formatter = logging.Formatter(fmt="%(asctime)s %(levelname)s: [%(name)s] %(message)s")

# Log all to file
rotate_handler = logging.handlers.RotatingFileHandler(str(logdir / 'debug.log'), backupCount=3, maxBytes=1024 * 1024)
rotate_handler.setFormatter(formatter)
rotate_handler.setLevel(logging.DEBUG)

root_logger.addHandler(rotate_handler)


def log_handled_exception(exc, msg, logger):
    try:
        raise exc
    except Exception:
        logger.exception(msg)


def infinity_sntl(_):
    return False


async def repeat_until(func, *, sentinel=infinity_sntl, period=1.0):
    while True:

        if asyncio.iscoroutinefunction(func):
            res = await func()
        else:
            res = func()

        if sentinel(res):
            return res

        await asyncio.sleep(period)


class CallbackProtocol(asyncio.DatagramProtocol):
    def __init__(self, receive_callback, logger, loop=None):
        asyncio.DatagramProtocol.__init__(self)

        if loop is None:
            loop = asyncio.get_event_loop()

        self.receive_callback = receive_callback
        self.logger = logger
        self.loop = loop
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.receive_callback(self.transport, data, addr)

    def error_received(self, exc):
        log_handled_exception(exc, "Error received", self.logger)

    def connection_lost(self, exc):
        if exc is not None:
            log_handled_exception(exc, "Socket closed, stop the event loop.", self.logger)
            self.loop.stop()

    def stop(self):
        if self.transport is None:
            raise RuntimeError("Can't stop not started protocol instance!")

        self.transport.close()


class ProxyServer:
    A2S_EMPTY_CHALLENGE = -1
    FRAGMENT_MAX_SIZE = 1200

    def __init__(self, local_addr, remote_addr, default_cache_lifetime=30, server_transport_lifetime=None):
        logger = logging.getLogger('%s:%s' % remote_addr)

        self.logger = logger
        self.local_addr = local_addr
        self.remote_addr = remote_addr
        self.default_cache_lifetime = default_cache_lifetime
        self.server_transport_lifetime = server_transport_lifetime

        self.resp_cache = {}
        self.fragments = pylru.lrucache(size=1024)

        self.stopped = False
        self.loop_tasks = []

        self._request_msg_classes = self._get_request_msg_classes()
        self._response_msg_classes = self._get_response_msg_classes()

        self._client_transport = None
        self._server_transport = None

    @property
    def loop(self):
        return asyncio.get_event_loop()

    async def _create_server_transport(self) -> asyncio.BaseTransport:
        transport, _ = await self.loop.create_datagram_endpoint(
            lambda: CallbackProtocol(self.on_server_response, logger=self.logger),
            remote_addr=self.remote_addr
        )  # WARN: reference cycle

        return transport

    async def _recreate_server_transport(self):
        old_server_transport = self._server_transport

        self._server_transport = await self._create_server_transport()

        if old_server_transport is not None:
            old_server_transport.close()

        return self._server_transport

    def _decode(self, packet, msg_classes):
        header = source.messages.Header.decode(packet)
        packet = header.raw_tail

        for cls in msg_classes:
            msg = cls.decode(packet, default=None)
            if msg is not None:
                return msg

        raise NotImplementedError

    @classmethod
    def _get_request_msg_classes(cls):
        return [
            source.messages.InfoRequest,
            source.messages.PlayersRequest,
            source.messages.RulesRequest,
        ]

    @classmethod
    def _get_response_msg_classes(cls):
        return [
            source.messages.InfoResponse,
            source.messages.PlayersResponse,
            source.messages.RulesResponse,
            source.messages.GetChallengeResponse,
        ]

    def decode_request(self, packet):
        return self._decode(packet, msg_classes=self._request_msg_classes)

    def decode_response(self, packet):
        return self._decode(packet, msg_classes=self._response_msg_classes)

    def handle_fragments(self, packet):
        header = source.messages.Header.decode(packet)
        if header['split'] != source.messages.SPLIT:
            return packet

        fragment = source.messages.Fragment.decode(header.raw_tail)
        packet_id = fragment['message_id']

        if packet_id in self.fragments:
            packet_fragments = self.fragments[packet_id]
        else:
            packet_fragments = []
            self.fragments[packet_id] = packet_fragments

        fragment_ids = set(f['fragment_id'] for f in packet_fragments)
        if fragment['fragment_id'] not in fragment_ids:
            packet_fragments.append(fragment)

        if len(packet_fragments) < fragment['fragment_count']:
            return None
        else:
            self.fragments.pop(packet_id, None)

            if len(packet_fragments) > fragment['fragment_count']:
                raise NotImplementedError

        packet_fragments.sort(key=lambda f: f['fragment_id'])
        return b''.join(f.raw_tail for f in packet_fragments)

    @classmethod
    def send(cls, packet, transport, addr=None, split_size=FRAGMENT_MAX_SIZE):
        if len(packet) <= split_size:
            transport.sendto(packet, addr)
            return

        message_id = random.randint(1, 2 ** 31 - 1)
        fragment_count = math.ceil(len(packet) / split_size)  # type: int
        mtu = split_size - (4 + (4 + 1 + 1 + 2))  # MAX_SIZE - (packet header + fragment header)

        packet_iter = iter(packet)

        for fragment_id in range(fragment_count):
            fragment_tail = bytes(itertools.islice(packet_iter, mtu))

            fragment_header = source.messages.Fragment().encode(
                message_id=message_id,
                fragment_count=fragment_count,
                fragment_id=fragment_id,
                mtu=mtu,
                split_header=True,
            )

            transport.sendto(
                b''.join((fragment_header, fragment_tail)),
                addr
            )

    def send_to_server(self, packet, split_size=FRAGMENT_MAX_SIZE):
        return self.send(packet, self._server_transport, split_size=split_size)

    @property
    def a2s_challenge(self):
        return self.resp_cache.get('a2s_challenge', self.A2S_EMPTY_CHALLENGE)

    def get_tasks(self):
        # Send requests to remote server (for update internal caches)
        # Response will be automatically handled by `on_server_response`
        return [
            asyncio.ensure_future(repeat_until(
                lambda: self.send_to_server(
                    source.messages.InfoRequest().encode(nosplit_header=True),
                ),
                period=self.default_cache_lifetime,
            )),
            asyncio.ensure_future(repeat_until(
                lambda: self.send_to_server(
                    source.messages.RulesRequest().encode(challenge=self.a2s_challenge, nosplit_header=True),
                ),
                period=self.default_cache_lifetime,
            )),
            asyncio.ensure_future(repeat_until(
                lambda: self.send_to_server(
                    source.messages.PlayersRequest().encode(
                        challenge=self.a2s_challenge, nosplit_header=True,
                    )
                ),
            )),
        ]

    def get_response_for(self, message):
        resp = None

        if isinstance(message, source.messages.InfoRequest):
            resp = self.resp_cache.get('a2s_info')
        elif isinstance(message, (source.messages.PlayersRequest, source.messages.RulesRequest)):
            challenge = message['challenge']

            if challenge == self.a2s_challenge:
                if isinstance(message, source.messages.PlayersRequest):
                    resp = self.resp_cache.get('a2s_players')
                elif isinstance(message, source.messages.RulesRequest):
                    resp = self.resp_cache.get('a2s_rules')
            elif self.a2s_challenge != self.A2S_EMPTY_CHALLENGE:
                # player request challenge number or we don't know who is it
                # return challenge number
                resp = source.messages.GetChallengeResponse().encode(
                    challenge=self.a2s_challenge, nosplit_header=True,
                )

        return resp

    def on_client_request(self, transport, data, addr):
        """
        @param transport: transport which used to receive data
        @param data: bytes object, contain received data
        @param addr: source address tuple (ip, port)
        """
        data = self.handle_fragments(data)
        if data is None:
            # data not ready
            return

        message = self.decode_request(data)
        self.on_client_message(transport, message, addr)

    def on_client_message(self, transport, message, addr):
        resp = self.get_response_for(message)

        if resp is None:
            return

        self.send(resp, transport, addr)

    def on_server_response_full(self, message, data):
        if isinstance(message, source.messages.InfoResponse):
            self.resp_cache['a2s_info'] = data
        elif isinstance(message, source.messages.PlayersResponse):
            self.resp_cache['a2s_players'] = data
        elif isinstance(message, source.messages.RulesResponse):
            self.resp_cache['a2s_rules'] = data
        elif isinstance(message, source.messages.GetChallengeResponse):
            self.resp_cache['a2s_challenge'] = message['challenge']

    def on_server_response(self, transport, data, addr):
        """
        @param transport: transport which used to receive data
        @param data: bytes object, contain received data
        @param addr: source address tuple (ip, port)
        """

        data = self.handle_fragments(data)
        if data is None:
            # data not ready
            return

        message = self.decode_response(data)
        self.on_server_response_full(message, data)

    @staticmethod
    def _get_cfg_addresses(cfg):
        bind_addr = cfg['bind-addr']
        bind_port = int(cfg['proxy-port'])
        server_addr = cfg['server-addr']
        server_port = int(cfg['server-port'])

        # local_addr, remote_addr
        return (bind_addr, bind_port), (server_addr, server_port)

    @classmethod
    def from_config(cls, cfg):
        local_addr, remote_addr = cls._get_cfg_addresses(cfg)

        settings = {
            'local_addr': local_addr,
            'remote_addr': remote_addr,
        }

        if 'default_cache_lifetime' in cfg:
            settings['default_cache_lifetime'] = int(cfg['default_cache_lifetime'])

        if 'server_transport_lifetime' in cfg:
            settings['server_transport_lifetime'] = int(cfg['server_transport_lifetime'])

        return cls(**settings)

    def stop(self):
        self.stopped = True

    async def run(self):
        loop = self.loop

        self._server_transport = await self._create_server_transport()

        client_transport, _ = await loop.create_datagram_endpoint(
            lambda: CallbackProtocol(self.on_client_request, logger=self.logger, loop=loop),
            local_addr=self.local_addr
        )

        recreate_server_transport_task = None
        if self.server_transport_lifetime is not None:
            recreate_server_transport_task = asyncio.ensure_future(
                repeat_until(self._recreate_server_transport, period=self.server_transport_lifetime)
            )
            recreate_server_transport_task.add_done_callback(lambda fut: log_future_exception(fut, self.logger))

        tasks = self.get_tasks()
        while not self.stopped:
            await asyncio.wait(tasks, timeout=1)

        for t in tasks:
            t.cancel()

        if recreate_server_transport_task is not None:
            recreate_server_transport_task.cancel()

        client_transport.close()
        self._server_transport.close()


class MasterServer:
    child = ProxyServer

    def __init__(self, servers=None):
        self._servers = servers

        self.stopped = False

    def stop(self):
        self.stopped = True

    def _create_tasks(self):
        return []

    async def run(self):
        tasks = []

        for server in self._servers:
            task = asyncio.ensure_future(server.run())
            task.add_done_callback(lambda fut: log_future_exception(fut, server.logger))

            tasks.append(task)

        tasks.extend(self._create_tasks())

        while not self.stopped:
            await asyncio.wait(tasks, timeout=1)

        for server in self._servers:
            server.stop()

        await asyncio.wait(tasks, timeout=1)

        for t in tasks:
            t.cancel()

    @classmethod
    def from_config(cls, cfg):
        servers = []

        for server_cfg in cfg.values():
            servers.append(cls.child.from_config(server_cfg))

        return cls(servers=servers)


class CSGOServer(ProxyServer):
    def __init__(self, aggregator=None, **kw):
        super().__init__(**kw)
        self.aggregator = aggregator

    def on_client_message(self, transport, message, addr):
        super().on_client_message(transport, message, addr)

        aggregator = self.aggregator
        if aggregator is not None:
            aggregator.aggregate(addr, message)


class CSGOMasterServer(MasterServer):
    child = CSGOServer

    def __init__(self, aggregator=None, **kw):
        super().__init__(**kw)

        if aggregator is None:
            aggregator = stats.CSGOAggregator()

        self._aggregator = aggregator

    async def run(self):
        for server in self._servers:
            server.aggregator = self._aggregator

        await super().run()

    def get_stats(self):
        return (
            'Stats (%s servers):\n' % len(self._servers)
            + self._aggregator.format_stats()
        )


def log_future_exception(future, logger):
    try:
        exc = future.exception()
    except asyncio.CancelledError as e:
        exc = e

    if exc is not None:
        log_handled_exception(exc, "Task interrupted!", logger)
    else:
        logger.info("Task done!")


async def main():
    from config import config

    csgo_master_server = None
    common_master_server = None

    tasks = []

    if 'csgo' in config:
        csgo_master_server = CSGOMasterServer.from_config(config['csgo'])

        def print_stats():
            os.system('clear')
            print(csgo_master_server.get_stats())

        print_stats_task = asyncio.ensure_future(repeat_until(
            print_stats,
            period=5,
        ))

        tasks.append(csgo_master_server.run())
        tasks.append(print_stats_task)

    if 'common' in config:
        common_master_server = MasterServer.from_config(config['common'])
        tasks.append(common_master_server.run())

    try:
        await asyncio.wait(tasks)
    finally:
        print("Stopping proxy servers...")

        for master in (csgo_master_server, common_master_server):
            if master is not None:
                master.stop()

        print("Done!")

    for task in tasks:
        task.cancel()


def _startup():
    from contextlib import suppress

    pid_fpath, *_ = __file__.rsplit('.', 1)
    pid_fpath += '.pid'

    ptrack = PIDTracker.from_file_path(pid_fpath)
    if ptrack.is_running():
        print("Daemon already running!")
        return

    with ptrack.track():
        if uvloop is not None:
            print("uvloop speedups enabled")
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        elif PY_35:
            print(
                "You can install uvloop to increase performance: \n"
                "# apt-get install python3-dev\n"
                "# python3 -m pip install uvloop"
            )

    loop = asyncio.get_event_loop()
    with suppress(KeyboardInterrupt, SystemExit):
        loop.run_until_complete(asyncio.ensure_future(main()))


if __name__ == '__main__':
    _startup()
