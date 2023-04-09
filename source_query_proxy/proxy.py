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

NO_RESPONSE = object()

retry_ConnError = backoff.on_exception(  # noqa: ignore=N816
    backoff.constant,
    ConnectionRefusedError,
    logger=None,
)


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

    def __iter__(self):
        return iter(
            k
            for k, v in self.data.items()
            # we need only ready values to get
            if not isinstance(v, asyncio.Future) or (v.done() and not v.cancelled())
        )

    def __getitem__(self, key):
        value = super().__getitem__(key)
        if not value.done() or value.cancelled():
            raise KeyError(key)
        return value.result()

    async def get_wait(self, key):
        if key not in self.data:
            fut = asyncio.Future()
            self.data[key] = fut
        else:
            fut = self.data[key]

        return await fut


class LastOkFailCounter:
    def __init__(
        self,
        fails_threshold: int,
        on_fails_threshold_reached: typing.Callable,
        on_fails_threshold_reset: typing.Callable,
    ):
        self._last_success_at = 0
        self._fails_in_row = 0
        self._fails_threshold_reached = True  # to run `on_fails_threshold_reset` on first `ok()` call
        self.fails_threshold = fails_threshold
        self.on_fails_threshold_reached = on_fails_threshold_reached
        self.on_fails_threshold_reset = on_fails_threshold_reset

    def ok(self):
        now = time.monotonic()
        if now < self._last_success_at:
            return

        self._last_success_at = now
        self._fails_in_row = 0
        if self._fails_threshold_reached:
            self._fails_threshold_reached = False
            self.on_fails_threshold_reset()

    def fail(self):
        now = time.monotonic()
        if now < self._last_success_at:
            return

        self._fails_in_row += 1
        if self._fails_in_row == self.fails_threshold:
            self._fails_threshold_reached = True
            self.on_fails_threshold_reached()


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
        self._okfail = LastOkFailCounter(
            fails_threshold=self.settings.max_a2s_fails_before_offline,
            on_fails_threshold_reached=self._on_offline,
            on_fails_threshold_reset=self._on_online,
        )
        self.online = False  # True - answer to client requests, False - ignore it

    def _on_online(self):
        self.logger.info('Server UP now')
        self.online = True

    def _on_offline(self):
        self.logger.warning('Server DOWN. Checking continued...')
        self.online = False

    # noinspection PyPep8Naming
    @property
    def retry_AnyError(self, log_level=logging.ERROR):  # noqa: ignore=N802
        return backoff.on_exception(
            backoff.constant,
            Exception,
            logger=self.logger,
            backoff_log_level=log_level,
            giveup=lambda e: isinstance(e, asyncio.CancelledError),
            giveup_log_level=logging.DEBUG,
        )

    async def _listen_client_requests(self):
        self.logger.info('Binding (%s) ... ', self.listen_addr)
        async with (await self.bind(self.listen_addr)) as listening:
            self.logger.info('Binding (%s) ... done!', self.listen_addr)
            self.logger.info('Listen for client requests on %s ...', self.listen_addr)
            while True:
                request, data, addr = await listening.recv_packet()
                if request is None:
                    self.logger.warning(
                        'Packet ignored. Broken data was received: data[:150]=%s',
                        data[:150],
                    )
                    continue

                if addr[1] == 0:
                    # FIXME: https://github.com/MagicStack/uvloop/issues/338
                    continue

                if not self.online:
                    continue

                response = self.get_response_for(request, None)
                if response is None:
                    self.logger.warning('No response for %s', request)
                    continue
                if response is NO_RESPONSE:
                    continue

                await listening.send_packet(response, addr=addr)

    def get_tasks(self):
        funcs = [
            self._listen_client_requests,
            self._update_info,
            self._update_players,
        ]
        if not self.settings.no_a2s_rules:
            funcs.append(self._update_rules)

        return [asyncio.create_task(self.retry_AnyError(func)()) for func in funcs]

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
                if old_challenge not in (self.A2S_EMPTY_CHALLENGE, None):
                    self.logger.warning(
                        'Challenge number changed: %s -> %s',
                        old_challenge,
                        message['challenge'],
                    )

                old_challenge = a2s_challenge
                a2s_challenge = message['challenge']
                continue

            break

        return message, data, addr, a2s_challenge

    @retry_ConnError
    async def _update_info(self):
        logger = self.logger.getChild('update-info')
        request = messages.InfoRequestV2()

        while True:
            async with (await connect(self.server_addr)) as client:
                logger.debug('Send request to %s (client port=%s)', self.server_addr, client.sockname[1])

                try:
                    message, data, addr, a2s_challenge = await self.send_recv_packet(
                        client,
                        request,
                        timeout=max(
                            self.settings.a2s_response_timeout,
                            self.settings.a2s_info_cache_lifetime,
                        ),
                    )
                except asyncio.TimeoutError:
                    self._okfail.fail()
                else:
                    self._okfail.ok()
                    self.resp_cache['a2s_info'] = data

            await asyncio.sleep(self.settings.a2s_info_cache_lifetime)

    @retry_ConnError
    async def _update_rules(self):
        logger = self.logger.getChild('update-rules')

        while True:
            async with (await connect(self.server_addr)) as client:
                logger.debug('Sent request to %s (client port=%s)', self.server_addr, client.sockname[1])

                request = messages.RulesRequest(challenge=self.A2S_EMPTY_CHALLENGE)

                try:
                    message, data, addr, a2s_challenge = await self.send_recv_packet(
                        client,
                        request,
                        timeout=max(
                            self.settings.a2s_response_timeout,
                            self.settings.a2s_rules_cache_lifetime,
                        ),
                    )
                except asyncio.TimeoutError:
                    self._okfail.fail()
                else:
                    self._okfail.ok()
                    self.resp_cache['a2s_rules'] = data

            await asyncio.sleep(self.settings.a2s_rules_cache_lifetime)

    @retry_ConnError
    async def _update_players(self):
        logger = self.logger.getChild('update-players')

        while True:
            async with (await connect(self.server_addr)) as client:
                logger.debug('Send request to %s (client port=%s)', self.server_addr, client.sockname[1])

                request = messages.PlayersRequest(challenge=self.A2S_EMPTY_CHALLENGE)
                try:
                    message, data, addr, a2s_challenge = await self.send_recv_packet(
                        client,
                        request,
                        timeout=max(
                            self.settings.a2s_response_timeout,
                            self.settings.a2s_players_cache_lifetime,
                        ),
                    )
                except asyncio.TimeoutError:
                    self._okfail.fail()
                else:
                    self._okfail.ok()
                    self.resp_cache['a2s_players'] = data

            await asyncio.sleep(self.settings.a2s_players_cache_lifetime)

    def get_response_for(self, message, default) -> typing.Optional[bytes]:
        resp = default

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
        tasks = self.get_tasks()
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            exc = task.exception() if not task.cancelled() else None
            self.logger.error('Task unexpectedly completed', exc_info=exc)  # noqa: ignore=G201

        for task in pending:
            task.cancel()

    async def wait_ready(self):
        """Wait until all internals being ready to start"""
        resp_cache = self.resp_cache = AwaitableDict(self.resp_cache)

        coros = [
            resp_cache.get_wait('a2s_info'),
            resp_cache.get_wait('a2s_players'),
        ]
        if not self.settings.no_a2s_rules:
            coros.append(resp_cache.get_wait('a2s_rules'))

        graceful_period = self.settings.wait_ready_graceful_period

        try:
            with async_timeout.timeout(graceful_period):
                await asyncio.gather(*coros)
        except asyncio.TimeoutError:
            self.logger.warning('Graceful period for wait ready exceeded. Skip waiting')
        finally:
            self.resp_cache = dict(resp_cache)
