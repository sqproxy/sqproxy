import asyncio
import collections
import functools
import logging
import random
import time
import typing

import async_timeout
import backoff

from . import config
from .source import messages
from .transport import bind
from .transport import connect

MAX_SIZE_32 = 2 ** 31 - 1


class AwaitableDict(collections.UserDict):
    """Оборачивает все значения в asyncio.Future
    таким образом можно дождаться появления нужного значения в словаре
    """

    def __setitem__(self, key, value):
        if key in self:
            fut = self.data[key]
            if fut.done():
                fut = self.data[key] = asyncio.Future()
            fut.set_result(value)
        else:
            fut = asyncio.Future()
            fut.set_result(value)
            self.data[key] = fut

    def __getitem__(self, key):
        value = super().__getitem__(key)
        if not value.done():
            raise KeyError(key)
        return value.result()

    async def get_wait(self, key):
        if key not in self.data:
            fut = asyncio.Future()
            self.data[key] = fut
        else:
            fut = self.data[key]

        return await fut


class QueryProxy:
    A2S_EMPTY_CHALLENGE = -1
    connect = functools.partial(connect)
    bind = functools.partial(bind)

    def __init__(self, settings: config.ServerModel, name: str = None):
        listen_addr = (str(settings.network.bind_ip), settings.network.bind_port)
        server_addr = (str(settings.network.server_ip), settings.network.server_port)

        if name is None:
            name = '%s:%s' % listen_addr

        self.listen_addr = listen_addr
        self.server_addr = server_addr
        self.resp_cache = {}
        self.our_a2s_challenge = random.randint(1, MAX_SIZE_32)
        self.settings = settings
        self.logger = logging.getLogger(name)

    # noinspection PyPep8Naming
    @property
    def retry_TimeoutError(self):  # noqa: ignore=N802
        return backoff.on_exception(backoff.constant, asyncio.TimeoutError, logger=self.logger)

    async def listen_client_requests(self):
        self.logger.info('Binding ... ')
        async with (await self.bind(self.listen_addr)) as listening:
            self.logger.info('Binding ... done!')
            self.logger.info('Listen for client requests ...')
            while True:
                request, data, addr = await listening.recv_packet()
                if request is None:
                    self.logger.warning(
                        'Broken data was received: data[:150]=%s', data[:150],
                    )
                    continue

                if addr[1] == 0:
                    # FIXME: https://github.com/MagicStack/uvloop/issues/338
                    continue

                response = self.get_response_for(request)
                if response is None:
                    self.logger.warning('No response for %s', request)
                    continue

                await listening.send_packet(response, addr=addr)

    async def update_server_query_cache(self):
        coros = [
            self.retry_TimeoutError(self._update_info)(),
            self.retry_TimeoutError(self._update_players)(),
        ]
        if not self.settings.no_a2s_rules:
            coros.append(self.retry_TimeoutError(self._update_rules)())

        return await asyncio.gather(*coros)

    async def send_recv_packet(self, client, packet: messages.Packet, timeout=None):
        """Send packet and wait for response for it

        In addition to call client.[send_packet(), recv_packet()] this method handle
        GetChallengeResponse logic

        :param client: connected client
        :param packet: any `messages.Packet` instance to send to
        :param timeout: how much wait response
            trigger asyncio.TimeoutError on exceeded
        :return: tuple (message, data, addr, new_challenge)
            `new_challenge` will be None if not present
        """
        old_challenge = packet.get('challenge')

        a2s_challenge = old_challenge
        while True:
            if a2s_challenge is not None:
                await client.send_packet(packet.encode(challenge=a2s_challenge))
            else:
                await client.send_packet(packet.encode())

            start = time.monotonic()
            with async_timeout.timeout(timeout):
                message, data, addr = await client.recv_packet()
                self.logger.debug('Got %s for %ss', message.__class__.__name__, time.monotonic() - start)

            if isinstance(message, messages.GetChallengeResponse):
                if old_challenge is not self.A2S_EMPTY_CHALLENGE:
                    self.logger.warning(
                        'Challenge number changed: %s -> %s', old_challenge, message['challenge'],
                    )

                a2s_challenge = message['challenge']
                continue

            break

        return message, data, addr, a2s_challenge

    async def _update_info(self):
        logger = self.logger.getChild('update-info')
        request = messages.InfoRequest().encode()

        get_time = asyncio.get_event_loop().time
        connection_lifetime = self.settings.src_query_port_lifetime
        while True:
            connection_eta = get_time() + connection_lifetime

            async with (await connect(self.server_addr)) as client:
                logger.debug('Connected to %s (client port=%s)', self.server_addr, client.sockname[1])

                while get_time() < connection_eta:
                    await client.send_packet(request)
                    start = time.monotonic()
                    with async_timeout.timeout(connection_lifetime):
                        message, data, addr = await client.recv_packet()
                        self.logger.debug('Got %s for %ss', message.__class__.__name__, time.monotonic() - start)
                    self.resp_cache['a2s_info'] = data
                    await asyncio.sleep(self.settings.a2s_info_cache_lifetime)

                logger.debug('Connection expired. Closing')

    async def _update_rules(self):
        logger = self.logger.getChild('update-rules')

        get_time = asyncio.get_event_loop().time
        connection_lifetime = self.settings.src_query_port_lifetime
        while True:
            connection_eta = get_time() + connection_lifetime

            async with (await connect(self.server_addr)) as client:
                logger.debug('Connected to %s (client port=%s)', self.server_addr, client.sockname[1])

                a2s_challenge = self.A2S_EMPTY_CHALLENGE
                while get_time() < connection_eta:
                    request = messages.RulesRequest(challenge=a2s_challenge)
                    message, data, addr, a2s_challenge = await self.send_recv_packet(
                        client, request, timeout=connection_lifetime,
                    )
                    self.resp_cache['a2s_rules'] = data
                    await asyncio.sleep(self.settings.a2s_rules_cache_lifetime)

                logger.debug('Connection expired. Closing')

    async def _update_players(self):
        logger = self.logger.getChild('update-players')

        get_time = asyncio.get_event_loop().time
        connection_lifetime = self.settings.src_query_port_lifetime
        while True:
            connection_eta = get_time() + connection_lifetime

            async with (await connect(self.server_addr)) as client:
                logger.debug('Connected to %s (client port=%s)', self.server_addr, client.sockname[1])

                a2s_challenge = self.A2S_EMPTY_CHALLENGE
                while get_time() < connection_eta:
                    request = messages.PlayersRequest(challenge=a2s_challenge)
                    message, data, addr, a2s_challenge = await self.send_recv_packet(
                        client, request, timeout=connection_lifetime,
                    )

                    self.resp_cache['a2s_players'] = data
                    await asyncio.sleep(self.settings.a2s_players_cache_lifetime)

                logger.debug('Connection expired. Closing')

    def get_response_for(self, message) -> typing.Optional[bytes]:
        resp = None

        if isinstance(message, messages.InfoRequest):
            resp = self.resp_cache.get('a2s_info')
        elif isinstance(message, (messages.PlayersRequest, messages.RulesRequest)):
            challenge = message['challenge']

            if challenge == self.our_a2s_challenge:
                if isinstance(message, messages.PlayersRequest):
                    resp = self.resp_cache.get('a2s_players')
                elif isinstance(message, messages.RulesRequest):
                    resp = self.resp_cache.get('a2s_rules')
            elif self.our_a2s_challenge != self.A2S_EMPTY_CHALLENGE:
                # player request challenge number or we don't know who is it
                # return challenge number
                resp = messages.GetChallengeResponse(challenge=self.our_a2s_challenge).encode()

        return resp

    async def run(self):
        done, pending = await asyncio.wait(
            [self.update_server_query_cache(), self.listen_client_requests()], return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            exc = task.exception() if not task.cancelled() else None
            self.logger.error('Task unexpectedly completed', exc_info=exc)  # noqa: ignore=G201

        for task in pending:
            task.cancel()

    async def wait_ready(self):
        """Wait until all internals being ready to start
        """
        resp_cache = self.resp_cache = AwaitableDict(self.resp_cache)

        await resp_cache.get_wait('a2s_info')
        await resp_cache.get_wait('a2s_players')
        if not self.settings.no_a2s_rules:
            await resp_cache.get_wait('a2s_rules')

        self.resp_cache = dict(resp_cache)
