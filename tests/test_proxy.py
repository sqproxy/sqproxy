import asyncio
import collections

import async_timeout
import pytest

from source_query_proxy.config import ServerModel
from source_query_proxy.proxy import QueryProxy
from source_query_proxy.source import messages
from source_query_proxy.transport import bind
from source_query_proxy.transport import connect

pytestmark = [pytest.mark.asyncio]


CACHE_MISS_LIFETIME = 0.1


@pytest.fixture()
async def server(addr_family):
    addr, _ = addr_family
    server = await bind(addr)
    yield server
    server.close()


@pytest.fixture(params=['default'])
def a2s_info_cache_lifetime(request) -> int:
    if request.param == 'default':
        return ServerModel.__fields__['a2s_info_cache_lifetime'].get_default()
    return request.param


@pytest.fixture(params=['default'])
def a2s_rules_cache_lifetime(request) -> int:
    if request.param == 'default':
        return ServerModel.__fields__['a2s_rules_cache_lifetime'].get_default()
    return request.param


@pytest.fixture(params=['default'])
def a2s_players_cache_lifetime(request) -> int:
    if request.param == 'default':
        return ServerModel.__fields__['a2s_players_cache_lifetime'].get_default()
    return request.param


@pytest.fixture()
def rust_info_response_bytes():
    return b'\xff\xff\xff\xffI\x11ZOZO.GG | X2/X5 | INSTA | REM | TP | KITS | WIPE 6.02\x00Procedural Map\x00rust\x00Rust\x00\x00\x00\x00<\x00dl\x00\x012215\x00\xb1om\x07\xcc\xf6ra7@\x01mp60,cp0,qp0,v2215,h986958cf,stok,born1581024860,gmrust,oxide,modded\x00J\xda\x03\x00\x00\x00\x00\x00'  # noqa: E501


@pytest.fixture()
def rust_rules_response_bytes():
    return b'\xff\xff\xff\xffE"\x00build\x0046638\x00description_0\x00\x00description_00\x00\xd0\xa1\xd0\xb5\xd1\x80\xd0\xb2\xd0\xb5\xd1\x80 \xd1\x81\xd0\xbe\xd0\xbe\xd0\xb1\xd1\x89\xd0\xb5\xd1\x81\xd1\x82\xd0\xb2\xd0\xb0 ZOZO.GG\\n\\n- \xd0\x9c\xd0\xb3\xd0\xbd\xd0\xbe\xd0\xb2\xd0\xb5\xd0\xbd\xd0\xbd\xd1\x8b\xd0\xb9 \xd0\xba\xd1\x80\xd0\xb0\xd1\x84\xd1\x82\\n- \xd0\xa0\xd0\xb5\xd0\xb9\xd1\x82\xd1\x8b: \xd1\x852 (\xd0\xb4\xd0\xb5\xd0\xbd\xd1\x8c) / \xd1\x855 (\xd0\xbd\xd0\xbe\xd1\x87\xd1\x8c)                     \x00description_01\x00           \\n- \xd0\xa0\xd0\xb5\xd0\xbc\xd1\x83\xd0\xb2 \xd1\x82\xd0\xbe\xd0\xbb\xd1\x8c\xd0\xba\xd0\xbe \xd0\xbd\xd0\xb0 \xd1\x81\xd0\xb2\xd0\xbe\xd0\xb8 \xd0\xbf\xd0\xbe\xd1\x81\xd1\x82\xd1\x80\xd0\xbe\xd0\xb9\xd0\xba\xd0\xb8\\n- \xd0\xa1\xd1\x82\xd0\xb0\xd1\x80\xd1\x82\xd0\xbe\xd0\xb2\xd1\x8b\xd0\xb5 \xd0\xbd\xd0\xb0\xd0\xb1\xd0\xbe\xd1\x80\xd1\x8b \xd0\xb4\xd0\xbb\xd1\x8f \xd0\xb2\xd1\x81\xd0\xb5\xd1\x85\x00description_02\x00\x00description_03\x00\x00description_04\x00\x00description_05\x00\x00description_06\x00\x00description_07\x00\x00description_08\x00\x00description_09\x00\x00description_10\x00\x00description_11\x00\x00description_12\x00\x00description_13\x00\x00description_14\x00\x00description_15\x00\x00ent_cnt\x0071167\x00fps\x00226\x00fps_avg\x00227.28\x00gc_cl\x00150\x00gc_mb\x001119\x00gmd\x00The default Rust survival gamemode\x00gmn\x00rust\x00gmt\x00Rust: Survival Mode\x00gmu\x00https://rust.facepunch.com\x00hash\x00986958cf\x00headerimage\x00http://i.imgur.com/1SHlsXX.jpg\x00pve\x00False\x00uptime\x0023944\x00url\x00http://zozo.gg/\x00world.seed\x004218819\x00world.size\x004000\x00'  # noqa: E501


@pytest.fixture()
def rust_players_response_bytes():
    return b'\xff\xff\xff\xffD\x01\x00MyHangryLord\x00\x00\x00\x00\x00\x17\\LD'


class GameServerMock:
    challenge = 0xBEEF
    server = None

    def __init__(self, info_response: bytes, players_response: bytes, rules_response: bytes):
        self.received_counter = collections.Counter()

        self.info_response = info_response
        self.players_response = players_response
        self.rules_response = rules_response

    async def run(self, server):
        assert self.server is None
        self.server = server

        while True:
            message, data, addr = await server.recv_packet()
            self.received_counter[message.__class__] += 1

            if isinstance(message, messages.InfoRequest):
                await server.send_bytes(self.info_response, addr=addr)
            elif isinstance(message, messages.RulesRequest):
                if message['challenge'] != self.challenge:
                    await server.send_packet(
                        messages.GetChallengeResponse(challenge=self.challenge).encode(), addr=addr
                    )
                else:
                    await server.send_bytes(self.rules_response, addr=addr)
            elif isinstance(message, messages.PlayersRequest):
                if message['challenge'] != self.challenge:
                    await server.send_packet(
                        messages.GetChallengeResponse(challenge=self.challenge).encode(), addr=addr
                    )
                else:
                    await server.send_bytes(self.players_response, addr=addr)
            else:
                raise NotImplementedError


@pytest.fixture()
async def game_server_mock(
    event_loop,
    server,
    rust_info_response_bytes,
    rust_rules_response_bytes,
    rust_players_response_bytes,
):
    game_server = GameServerMock(rust_info_response_bytes, rust_players_response_bytes, rust_rules_response_bytes)
    task = event_loop.create_task(game_server.run(server))
    task.add_done_callback(lambda fut: not fut.cancelled() and fut.result())
    yield game_server
    task.cancel()
    await asyncio.gather(task, loop=event_loop, return_exceptions=True)


@pytest.fixture()
async def game_server_proxy(
    event_loop,
    game_server_mock,
    a2s_info_cache_lifetime,
    a2s_players_cache_lifetime,
    a2s_rules_cache_lifetime,
):
    server_ip, server_port = game_server_mock.server.sockname
    proxy = QueryProxy(
        ServerModel(
            **{
                'meta': {},
                'network': {
                    'server_ip': server_ip,
                    'server_port': server_port,
                    'bind_ip': '127.0.0.1',
                    'bind_port': 27915,
                },
                'a2s_info_cache_lifetime': a2s_info_cache_lifetime,
                'a2s_players_cache_lifetime': a2s_players_cache_lifetime,
                'a2s_rules_cache_lifetime': a2s_rules_cache_lifetime,
            }
        )
    )
    task = event_loop.create_task(proxy.run())
    task.add_done_callback(lambda fut: not fut.cancelled() and fut.result())
    yield proxy
    task.cancel()
    await asyncio.gather(task, loop=event_loop, return_exceptions=True)


@pytest.mark.parametrize(
    'a2s_info_cache_lifetime',
    ['default', CACHE_MISS_LIFETIME],
    ids=['cache hit', 'cache misses'],
    indirect=True,
)
async def test_proxy_info(game_server_proxy, game_server_mock, a2s_info_cache_lifetime):
    assert game_server_proxy.resp_cache.get('a2s_info') is None
    assert game_server_mock.received_counter[messages.InfoRequest] == 0

    await game_server_proxy.wait_ready()

    client = await connect(('127.0.0.1', 27915))

    cache_misses = a2s_info_cache_lifetime == CACHE_MISS_LIFETIME

    for _ in range(2):
        await client.send_packet(messages.InfoRequest().encode())
        with async_timeout.timeout(1):
            message, data, addr = await client.recv_packet()

        assert isinstance(message, messages.InfoResponse)
        assert game_server_mock.info_response == game_server_proxy.resp_cache['a2s_info'] == data

    if cache_misses:
        assert game_server_mock.received_counter[messages.InfoRequest] > 1
    else:
        assert game_server_mock.received_counter[messages.InfoRequest] == 1


@pytest.mark.parametrize(
    'a2s_rules_cache_lifetime',
    ['default', CACHE_MISS_LIFETIME],
    ids=['cache hit', 'cache misses'],
    indirect=True,
)
async def test_proxy_rules(game_server_proxy, game_server_mock, a2s_rules_cache_lifetime):
    assert game_server_proxy.resp_cache.get('a2s_rules') is None
    assert game_server_mock.received_counter[messages.RulesRequest] == 0

    await game_server_proxy.wait_ready()

    client = await connect(('127.0.0.1', 27915))

    cache_misses = a2s_rules_cache_lifetime == CACHE_MISS_LIFETIME

    for _ in range(2):
        await client.send_packet(messages.RulesRequest(challenge=game_server_proxy.our_a2s_challenge).encode())
        with async_timeout.timeout(1):
            message, data, addr = await client.recv_packet()

        assert isinstance(message, messages.RulesResponse)
        assert game_server_mock.rules_response == game_server_proxy.resp_cache['a2s_rules'] == data

    if cache_misses:
        assert game_server_mock.received_counter[messages.RulesRequest] > 2
    else:
        # Challenge request + Real request
        assert game_server_mock.received_counter[messages.RulesRequest] == 2


@pytest.mark.parametrize(
    'a2s_players_cache_lifetime',
    ['default', CACHE_MISS_LIFETIME],
    ids=['cache hit', 'cache misses'],
    indirect=True,
)
async def test_proxy_players(game_server_proxy, game_server_mock, a2s_players_cache_lifetime):
    assert game_server_proxy.resp_cache.get('a2s_players') is None
    assert game_server_mock.received_counter[messages.PlayersRequest] == 0

    await game_server_proxy.wait_ready()

    client = await connect(('127.0.0.1', 27915))

    cache_misses = a2s_players_cache_lifetime == CACHE_MISS_LIFETIME

    for _ in range(2):
        await client.send_packet(messages.PlayersRequest(challenge=game_server_proxy.our_a2s_challenge).encode())
        with async_timeout.timeout(1):
            message, data, addr = await client.recv_packet()

        assert isinstance(message, messages.PlayersResponse)
        assert game_server_mock.players_response == game_server_proxy.resp_cache['a2s_players'] == data

    if cache_misses:
        assert game_server_mock.received_counter[messages.PlayersRequest] > 2
    else:
        # Challenge request + Real request
        assert game_server_mock.received_counter[messages.PlayersRequest] == 2
