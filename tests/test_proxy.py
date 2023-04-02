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


@pytest.fixture()
def css_rules_response_bytes__fragmented__compressed():
    return b'\xfe\xff\xff\xffL\x80\x00\x80\x01\x00"\x06\x00\x00\xbc\x06[\x18BZh91AY&SY\x06\x82\x1b\x00\x00\x03\x11_\x80\xc0\x00@\x0f\x7f\xe0oS\xc9\x10\xbf\xef\xff\xf0\x00\x00\xd0\x038\xa9oS\xab\xb2\xd8\xc3\x12jh\x02`A\r\x00\xd1\xea\x004\xf5\x00i\x06\x9a\nz\x8d\x01\xa0\x00\x00\x00\x000\x84HOH\x03 h\x00\x00\x00\x0c\x00\x00\x00\x00\xd0h\x03@4\x02H\x814\x9e\x9a#F\xa2~\x94h\x00\x00\x00\xf5;\xfa\xbd}\xdf\xe7\xc3K\xba\x18p\xfd\xe0W\xa7\xb7\xa4\xda\xf3\x84B\xb4\xd2\x8c)\x08 ZF\x02\x9c\xd89y&D|\x05\x7f\xea\xea\xb6M\xdf\xb44b\xf4g\xc8\x9e\xd2\x12R\x0b\x81\x1f\x05\x01\x00\x96\xaeH\xe4\xcdZ\xa42\x96U\x91J\x12\x90\x80\xcbz\x84\x08\xfbdc\xe3\xf5\xc1\xfb\xf3?\xe6Q\x11\\y\xad\xd7\xddg\xea\xc9^\xc8\x00\xd8I\x94\x1c$P\x82\xf9\xb2s\x04\x04\x99\x93\x08j\xfb,\x89J\x834\x9b-\'\x15\xbf\x02\xd3B\xc8\x10\xa50;P\x10\x8aF\x08\x9c\xd8\xe6\xefm\r:\xb1\x0c\xd4P\x99}\xc5\xaeA\xeeD1\xea\x95\xa1N\x86\x8c7\x8c\x88\x84\xaa\x03A\x13\xef\x1e\x1ai7B\xdd52\xd7\xde\x92T\x0f2w\x88$\x12])\xf7/\xcbQf\x85\x90i\xa4\xd9m\x10\xb9S0\xc32\xc0f\x0b\xd37\xf0~o\x0bS\xb4\xc0\xa0\xb0t\x811\x8a\xbb\xa8\x13\x94\x83\x11\\\xd3\xdc\x1au\x0cJ1\n\x0e\xf0D\xb1\x99g\x8c2]\xcaZY\r\xcc\xc0\xc0)bnP\xac\x99?4IL\xa1\x04d7\xed\x04\x16 \x96j\xbd\x06\xaaCIN\x96H\xb1\xa6k\'\xbcw\x99\xbc\x94D\x84\x12\xb4\x18\xc2\xf6\x90\xa5\xb2Of\x8d\xf4\xd3\xa5\x87h\x7f\xb3\x99\xd9\x82s\xa4\xf7\x926\x8c6v&\xb5C\xa3\x1a\xf6O\x1f\xc7cx\xcd\x19\xb6\x08\xa6\x89\xfe\xfb\xa2+\x8f\x15UW\xba1~\x96\x05\x7f,\x1ei\xb1\xbcQY9\x0b96s\x8cw-H\xc5\x01=l%4\x1ci\x83\xedlov\xe5\xa5\xf0\x91\xcd\x97\x18\xd7%[\xae\x896$\xc1\xd6\x18V,!\x98\x8a\xb1\xfdZ\xf3\x8c\xf6]\xd7;Q\xaaT,j\x95;\x8b\xc3\xaa\xd5*.Es9\xbe2`\xe7TE\xe8%\x950B\x1e\x0f\x85^\xa3a\x04D \\\x0cq\xcc#H\x1a\x11t\x16w\xbf\x02\x89\x01\x13\x9bU\x99\x15\x19\xd0Gw\x18\x9dc#\xad\xe2Bm@\xads\xf4tZ\xc1g\xcc^\xbe\xbd\xfdL\xb4\xb2I\xb0\x93\xbbnJ\x0e]J\x9bJ\xafB\xf2?>-\'<\xb36\xd5:A\x0e\xfd\x95B$\x8aQ\x19\xef\xaf\xbdZ09s2\xd6\x92[\xdc\x96G\x0c\x9c\x04\xe0\x8cXG\x10w\x08\xd0\x1cl\xe2\xd2\x12f\xaf\x85Ov\xfb\xa9\xfeM\x1dlv\xa9\xaf\xc7"\xdc\x1a\xca\xad\x9c\x83V\xb2,b\x16\xd7Y\x9bAs\xe0\xa0^\x18#\xc3\xc3\x91\x03!\n\xfa-\xd6#\x96\xab\xca\xca\xb1\x8ds\xd2\x02\x98\r\x94\x8aAD\x8b{\xa7\xca\x9f\xbb\x1c5\x19r\xc5\xf8B\xf6\x8b\x04\x8fN\x9c\x8e/N\xd0\x9a\x86.a|\xdc\xd0\x9c\xc1ra\x99#\x124\x056\x8e\x91EX)4(\xd9\x8a\n\xea\xef,$*\xbf\x8e?\xe2\xeeH\xa7\n\x12\x00\xd0C`\x00'  # noqa: E501


class GameServerMock:
    challenge = 0xBEEF
    server = None

    def __init__(self, info_response: bytes, players_response: bytes, rules_response: bytes):
        self.received_counter = collections.Counter()

        self.info_response = info_response
        self.players_response = players_response
        self.rules_response = rules_response

        # Accept only A2S_INFO with challenge number
        self.info_challenge_required = False

    async def run(self, server):  # noqa: C901
        assert self.server is None
        self.server = server

        while True:
            message, data, addr = await server.recv_packet()
            self.received_counter[message.__class__] += 1

            if isinstance(message, messages.InfoRequest):
                if not self.info_challenge_required:
                    await server.send_bytes(self.info_response, addr=addr)
                else:
                    if message.get('challenge') != self.challenge:
                        await server.send_packet(
                            messages.GetChallengeResponse(challenge=self.challenge).encode(), addr=addr
                        )
                    else:
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
    await asyncio.gather(task, return_exceptions=True)


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
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize(
    'a2s_info_cache_lifetime',
    ['default', CACHE_MISS_LIFETIME],
    ids=['cache hit', 'cache misses'],
    indirect=True,
)
@pytest.mark.parametrize('info_challenge_required', [False, True], ids=['no-challenge', 'challenge'])
async def test_proxy_info(game_server_proxy, game_server_mock, a2s_info_cache_lifetime, info_challenge_required):
    game_server_mock.info_challenge_required = info_challenge_required

    assert game_server_proxy.resp_cache.get('a2s_info') is None
    assert game_server_mock.received_counter[messages.InfoRequest] == 0

    await asyncio.wait_for(game_server_proxy.wait_ready(), timeout=1)

    client = await connect(('127.0.0.1', 27915))

    cache_misses = a2s_info_cache_lifetime == CACHE_MISS_LIFETIME

    for _ in range(2):
        await client.send_packet(messages.InfoRequest().encode())
        with async_timeout.timeout(1):
            message, data, addr = await client.recv_packet()

        assert isinstance(message, messages.InfoResponse)
        assert game_server_mock.info_response == game_server_proxy.resp_cache['a2s_info'] == data

        if cache_misses:
            # wait cache updated
            await asyncio.sleep(CACHE_MISS_LIFETIME * 2)

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

    await asyncio.wait_for(game_server_proxy.wait_ready(), timeout=1)

    client = await connect(('127.0.0.1', 27915))

    cache_misses = a2s_rules_cache_lifetime == CACHE_MISS_LIFETIME

    for _ in range(2):
        await client.send_packet(messages.RulesRequest(challenge=game_server_proxy.our_a2s_challenge).encode())
        with async_timeout.timeout(1):
            message, data, addr = await client.recv_packet()

        assert isinstance(message, messages.RulesResponse)
        assert game_server_mock.rules_response == game_server_proxy.resp_cache['a2s_rules'] == data

        if cache_misses:
            # wait cache updated
            await asyncio.sleep(CACHE_MISS_LIFETIME * 2)

    if cache_misses:
        assert game_server_mock.received_counter[messages.RulesRequest] > 2
    else:
        # Challenge request + Real request
        assert game_server_mock.received_counter[messages.RulesRequest] == 2


async def test_proxy_compressed_rules(
    game_server_proxy,
    game_server_mock,
    css_rules_response_bytes__fragmented__compressed,
):
    game_server_mock.rules_response = css_rules_response_bytes__fragmented__compressed

    assert game_server_proxy.resp_cache.get('a2s_rules') is None
    assert game_server_mock.received_counter[messages.RulesRequest] == 0

    await asyncio.wait_for(game_server_proxy.wait_ready(), timeout=1)

    client = await connect(('127.0.0.1', 27915))

    await client.send_packet(messages.RulesRequest(challenge=game_server_proxy.our_a2s_challenge).encode())
    with async_timeout.timeout(1):
        message, data, addr = await client.recv_packet()

    assert isinstance(message, messages.RulesResponse)
    assert message.values['response_type'] == 69
    assert message.values['rule_count'] == 77


@pytest.mark.parametrize(
    'a2s_players_cache_lifetime',
    ['default', CACHE_MISS_LIFETIME],
    ids=['cache hit', 'cache misses'],
    indirect=True,
)
async def test_proxy_players(game_server_proxy, game_server_mock, a2s_players_cache_lifetime):
    assert game_server_proxy.resp_cache.get('a2s_players') is None
    assert game_server_mock.received_counter[messages.PlayersRequest] == 0

    await asyncio.wait_for(game_server_proxy.wait_ready(), timeout=1)

    client = await connect(('127.0.0.1', 27915))

    cache_misses = a2s_players_cache_lifetime == CACHE_MISS_LIFETIME

    for _ in range(2):
        await client.send_packet(messages.PlayersRequest(challenge=game_server_proxy.our_a2s_challenge).encode())
        with async_timeout.timeout(1):
            message, data, addr = await client.recv_packet()

        assert isinstance(message, messages.PlayersResponse)
        assert game_server_mock.players_response == game_server_proxy.resp_cache['a2s_players'] == data

        if cache_misses:
            # wait cache updated
            await asyncio.sleep(CACHE_MISS_LIFETIME * 2)

    if cache_misses:
        assert game_server_mock.received_counter[messages.PlayersRequest] > 2
    else:
        # Challenge request + Real request
        assert game_server_mock.received_counter[messages.PlayersRequest] == 2
