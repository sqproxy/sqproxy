import asyncio
import itertools
import logging
import math
import random
import typing

import pylru
from asyncio_dgram.aio import DatagramStream
from asyncio_dgram.aio import Protocol

from .source import messages

MAX_SIZE_32 = 2 ** 31 - 1

logger = logging.getLogger('sqproxy.transport')


class UnknownRequest(Exception):
    pass


class BrokenPacketError(Exception):  # FIXME: message is app layer and packet is transport layer
    def __init__(self, raw_data, addr):
        self.raw_data = raw_data
        self.addr = addr


class SourceDatagramStream(DatagramStream):
    FRAGMENT_MAX_SIZE = 1200
    MAX_FRAGMENTS_PER_PACKET = 100

    def __init__(self, transport, recvq, excq, drained):
        super().__init__(transport, recvq, excq, drained)
        self.fragments = pylru.lrucache(size=1024)

    def handle_fragments(self, packet):
        header = messages.Header.decode(packet)
        if header['split'] != messages.SPLIT:
            return packet

        fragment = messages.Fragment.decode(header.raw_tail)
        packet_id = fragment['message_id']

        if packet_id in self.fragments:
            fragment_count, packet_fragments = self.fragments[packet_id]
        else:
            fragment_count = fragment['fragment_count']
            if fragment_count > self.MAX_FRAGMENTS_PER_PACKET:
                logger.warning(
                    'Packet fragment count more than our limit: %s > %s.' 'Packet will be trimmed',
                    fragment_count,
                    self.MAX_FRAGMENTS_PER_PACKET,
                )
                fragment_count = self.MAX_FRAGMENTS_PER_PACKET

            packet_fragments = []
            self.fragments[packet_id] = fragment_count, packet_fragments

        fragment_ids = {f['fragment_id'] for f in packet_fragments}
        if fragment['fragment_id'] not in fragment_ids:
            packet_fragments.append(fragment)

        if len(packet_fragments) < fragment_count:
            return None

        self.fragments.pop(packet_id, None)
        packet_fragments.sort(key=lambda f: f['fragment_id'])
        return b''.join(f.raw_tail for f in packet_fragments)

    async def send_packet(self, packet, addr=None, split_size=FRAGMENT_MAX_SIZE):
        if len(packet) <= split_size:
            await self.send(packet, addr)
            return

        message_id = random.randint(1, MAX_SIZE_32)
        fragment_count = math.ceil(len(packet) / split_size)  # type: int
        mtu = split_size - (4 + (4 + 1 + 1 + 2))  # MAX_SIZE - (packet header + fragment header)

        packet_iter = iter(packet)

        for fragment_id in range(fragment_count):
            fragment_tail = bytes(itertools.islice(packet_iter, mtu))

            fragment_header = messages.Fragment().encode(
                message_id=message_id,
                fragment_count=fragment_count,
                fragment_id=fragment_id,
                mtu=mtu,
                split_header=True,
            )

            await self.send(b''.join((fragment_header, fragment_tail)), addr)

    async def recv_packet(self):
        while True:
            data, addr = await super().recv()

            try:
                data = self.handle_fragments(data)
            except messages.BrokenMessageError:
                raise BrokenPacketError(data, addr)

            if data is None:
                # data not ready
                continue

            return data, addr

    async def send_bytes(self, data, addr=None):
        """Alias for `send()`, use it instead `send()`
         to explicit difference from `send_packet()`
        """
        return await self.send(data, addr)

    async def recv_bytes(self):
        """Alias for `recv()`, use it instead `recv()`
         to explicit difference from `recv_packet()`
        """
        return await self.recv()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.close()


def decode_packet(packet, msg_classes):
    header = messages.Header.decode(packet)
    packet = header.raw_tail

    for cls in msg_classes:
        msg = cls.decode(packet, default=None)
        if msg is not None:
            return msg

    return None


class SourceDatagramServer(SourceDatagramStream):
    request_message_classes = (
        messages.InfoRequest,
        messages.PlayersRequest,
        messages.RulesRequest,
    )

    def decode_request(self, packet):
        return decode_packet(packet, msg_classes=self.request_message_classes)

    async def recv_packet(self):
        try:
            data, addr = await super().recv_packet()
        except BrokenPacketError as exc:
            return None, exc.raw_data, exc.addr

        message = self.decode_request(data)
        return message, data, addr


class SourceDatagramClient(SourceDatagramStream):
    response_message_classes = (
        messages.InfoResponse,
        messages.PlayersResponse,
        messages.RulesResponse,
        messages.GetChallengeResponse,
    )

    def decode_response(self, packet):
        return decode_packet(packet, msg_classes=self.response_message_classes)

    async def recv_packet(self):
        while True:
            try:
                data, addr = await super().recv_packet()
            except BrokenPacketError as exc:
                return None, exc.raw_data, exc.addr

            message = self.decode_response(data)
            return message, data, addr


SourceDatagramServerType = typing.TypeVar('SourceDatagramServerType', bound=SourceDatagramServer)


async def bind(addr, *, cls: typing.Type[SourceDatagramServerType] = None) -> SourceDatagramServerType:
    """
    Bind a socket to a local address for datagrams.  The socket will be either
    AF_INET or AF_INET6 depending upon the type of address specified.

    @param addr - For AF_INET or AF_INET6, a tuple with the the host and port to
                  to bind; port may be set to 0 to get any free port.
    @param cls  - implementation of server SourceDatagram protocol
    @return     - A SourceDatagramServer instance
    """
    loop = asyncio.get_event_loop()
    recvq = asyncio.Queue()
    excq = asyncio.Queue()
    drained = asyncio.Event()

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: Protocol(recvq, excq, drained), local_addr=addr, reuse_address=False
    )

    if cls is None:
        cls = SourceDatagramServer

    return cls(transport, recvq, excq, drained)


SourceDatagramClientType = typing.TypeVar('SourceDatagramClientType', bound=SourceDatagramClient)


async def connect(addr, *, cls: typing.Type[SourceDatagramClientType] = None) -> SourceDatagramClientType:
    """
    Connect a socket to a remote address for datagrams.  The socket will be
    either AF_INET or AF_INET6 depending upon the type of host specified.

    @param addr - For AF_INET or AF_INET6, a tuple with the the host and port to
                  to connect to.
    @param cls  - implementation of client SourceDatagram protocol
    @return     - A SourceDatagramClient instance
    """
    loop = asyncio.get_event_loop()
    recvq = asyncio.Queue()
    excq = asyncio.Queue()
    drained = asyncio.Event()

    transport, protocol = await loop.create_datagram_endpoint(lambda: Protocol(recvq, excq, drained), remote_addr=addr)

    if cls is None:
        cls = SourceDatagramClient

    return cls(transport, recvq, excq, drained)
