import pytest

from source_query_proxy.source import messages
from source_query_proxy.transport import SourceDatagramClient
from source_query_proxy.transport import SourceDatagramServer
from source_query_proxy.transport import bind
from source_query_proxy.transport import connect

pytestmark = [pytest.mark.asyncio]


@pytest.fixture()
async def server(addr_family) -> SourceDatagramServer:
    addr, _ = addr_family
    server = await bind(addr)
    yield server
    server.close()


@pytest.fixture()
def client_socket(udp_socket, addr_family):
    addr, _ = addr_family
    udp_socket.bind(addr)
    yield udp_socket
    udp_socket.close()


@pytest.fixture()
async def client(client_socket) -> SourceDatagramClient:
    client = await connect(client_socket.getsockname()[:2])
    yield client
    client.close()


@pytest.fixture()
def server_socket(udp_socket, server):
    udp_socket.connect(server.sockname)
    yield udp_socket
    udp_socket.close()


@pytest.mark.parametrize('addr_family', ['INET', 'INET6'], indirect=True)
async def test_source_server_recv_info(server_socket, server, addr_family):
    assert messages.InfoRequest().encode() == messages.InfoRequestV2().encode()
    server_socket.send(messages.InfoRequest().encode())
    request, data, addr = await server.recv_packet()
    assert isinstance(request, messages.InfoRequest), request
    assert addr == server_socket.getsockname()


@pytest.mark.parametrize('addr_family', ['INET', 'INET6'], indirect=True)
async def test_source_server_recv_info_with_challenge(server_socket, server, addr_family):
    server_socket.send(messages.InfoRequestV2(challenge=0xBEEF).encode())
    request, data, addr = await server.recv_packet()
    assert isinstance(request, messages.InfoRequestV2), request
    assert addr == server_socket.getsockname()


@pytest.mark.parametrize('addr_family', ['INET', 'INET6'], indirect=True)
async def test_source_server_recv_players(server_socket, server, challenge, addr_family):
    server_socket.send(messages.PlayersRequest(challenge=challenge).encode())
    request, data, addr = await server.recv_packet()
    assert isinstance(request, messages.PlayersRequest), request
    assert addr == server_socket.getsockname()


@pytest.mark.parametrize('addr_family', ['INET', 'INET6'], indirect=True)
async def test_source_server_recv_rules(server_socket, server, challenge, addr_family):
    server_socket.send(messages.RulesRequest(challenge=challenge).encode())
    request, data, addr = await server.recv_packet()
    assert isinstance(request, messages.RulesRequest), request
    assert addr == server_socket.getsockname()


@pytest.mark.parametrize('addr_family', ['INET', 'INET6'], indirect=True)
async def test_source_server_recv_unknown_request(server_socket, server, addr_family):
    # valid header, unknown data
    server_socket.send(b'\xFF\xFF\xFF\xFF\0\0\0\0')
    message, data, addr = await server.recv_packet()
    assert message is None


@pytest.mark.skip('TODO')
@pytest.mark.parametrize('addr_family', ['INET', 'INET6'], indirect=True)
async def test_source_server_recv_fragmented_request(addr_family):
    ...


@pytest.mark.parametrize('addr_family', ['INET', 'INET6'], indirect=True)
async def test_source_client_send_request(client_socket, client, addr_family):
    await client.send_bytes(b'hi')
    got, client_addr = client_socket.recvfrom(4)
    assert got == b'hi'
