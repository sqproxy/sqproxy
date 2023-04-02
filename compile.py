import ipaddress

SOURCE = """
#include <linux/bpf.h>

#include <linux/in.h>
#include <linux/ip.h>
#include <linux/udp.h>
#include <linux/if_ether.h>
#include <uapi/linux/ipv6.h>

#include <bcc/proto.h>
#include <bcc/helpers.h>

#define UDP_PAYLOAD_OFFSET sizeof(struct ethernet_t) + sizeof(struct ip_t) + sizeof(struct udp_t);

BPF_HASH(gameserver2proxy_port, u16, u16, 128);
BPF_HASH(proxy2gameserver_port, u16, u16, 128);

#pragma pack(push)
#pragma pack(1)
struct _addr_key {
  u32 ip;
  u16 port;
};
#pragma pack(pop)

typedef struct _addr_key addr_key_t;

BPF_HASH(addr_gameserver2proxy_port, addr_key_t, u16, 128);
BPF_HASH(addr_proxy2gameserver_port, addr_key_t, u16, 128);

BPF_HASH(server_versions, u16, u16, 32);
BPF_TABLE("lru_hash", u32, u16, client_versions, 10240);


int incoming(struct __sk_buff *skb) {
    u8 *cursor = 0;

    struct ethernet_t *ethernet = cursor_advance(cursor, sizeof(*ethernet));
    if (!(ethernet->type == ETH_P_IP)) {
        return TC_ACT_OK;
    }
    struct ip_t *ip = cursor_advance(cursor, sizeof(*ip));

    if (ip->nextp != IPPROTO_UDP) {
        return TC_ACT_OK;
    }

    struct udp_t *udp = cursor_advance(cursor, sizeof(*udp));

    if (!udp->crc) {
        // Attacker can miss checsum calculation
        // for performance reasons
        return TC_ACT_SHOT;
    }

    u32 ip_dst = ip->dst;
    u16 dport = udp->dport;

    #ifndef USE_IPPORT_KEY
        u16 *value = gameserver2proxy_port.lookup(&dport);
    #else
        addr_key_t addr = {.ip = ip_dst, .port = dport};
        u16 *value = addr_gameserver2proxy_port.lookup(&addr);
    #endif

    if (!value) {
        return TC_ACT_OK;
    }

    u16 proxy_port = *value;

    u32 payload_offset = sizeof(*ethernet) + sizeof(*ip) + sizeof(*udp);
    u32 payload_length = ip->tlen - (sizeof(*ip) + sizeof(*udp));

    if (payload_length < 5) {
        return TC_ACT_OK;
    }

    uint8_t data[5];
    u32 ret = bpf_skb_load_bytes(skb, payload_offset, data, 5);
    if (ret) {
        return TC_ACT_OK;
    }

    u32 client_addr = ip->src;
    return TC_ACT_OK;
}
"""


import argparse
import atexit
import contextlib
import logging.config
import os
import re
import sys
import time
import signal
from bcc import BPF
from ctypes import c_uint16
from ctypes import c_uint32
from ctypes import Structure
from pyroute2 import IPRoute, protocols, IPDB
from pyroute2.netlink.exceptions import NetlinkError


ipr = IPRoute()
log = logging.getLogger('main')

class AddrKey(Structure):
    _fields_ = [
        ('ip', c_uint32),
        ('port', c_uint16),
    ]


def main(interface=None):
    if interface is None:
        log.info('Interface not provided')
        interface = get_default_interface()
        log.info('Use interface for default route: %s', interface)

    ip_addrs = None  # list(all_ports.keys())

    ipdb = IPDB()
    ifindex = ipr.link_lookup(ifname=interface)[0]
    ifaddrs = [ipaddress.ip_address(addr) for addr, mask in ipdb.ipaddr[ifindex]]

    if ip_addrs is not None:
        unknown_ip_addresses = set(ip_addrs).difference(ifaddrs)
        if unknown_ip_addresses:
            raise RuntimeError(
                "Can not setup filtering. Given IPs not assigned to given interface: "
                "IPs={unknown_ip_addresses}, interface={interface}.\n"
                "Note: available addresses is {ifaddrs}".format(
                    unknown_ip_addresses=[str(x) for x in unknown_ip_addresses],
                    interface=interface,
                    ifaddrs=[str(x) for x in ifaddrs],
                ),
            )

    log.info('Building eBPF program ...')
    bpf = BPF(text=SOURCE, debug=1)

    fn_incoming = bpf.load_func("incoming", BPF.SCHED_ACT)
    fn_outgoing = bpf.load_func("outgoing", BPF.SCHED_ACT)

    log.info('Attach eBPF program to interface ...')
    reg_cleanup(ifindex)
    setup_incoming(fn_incoming, ifindex)
    setup_outgoing(fn_outgoing, ifindex)

    log.info('Running ...')
    while True:
        time.sleep(1)


def get_default_interface():
    ipdb = IPDB()

    try:
        interface = ipdb.interfaces[ipdb.routes['default']['oif']]
        return interface['ifname']
    finally:
        ipdb.release()


def cleanup(ifindex, safe=False):
    log.debug('Cleanup (%s)', ifindex)
    try:
        ipr.tc("del", "ingress", ifindex, "ffff:")
    except NetlinkError as exc:
        if not safe or exc.args[1] != 'Invalid argument':
            raise

    try:
        ipr.tc("del", "sfq", ifindex, "1:")
    except NetlinkError as exc:
        if not safe or exc.args[1] != 'Invalid argument':
            raise

    log.debug('Cleanup (%s) done', ifindex)


def reg_cleanup(ifindex):
    def _inner(_, __):
        cleanup(ifindex, safe=True)
        signal.default_int_handler(_, __)

    signal.signal(signal.SIGTERM, _inner)
    signal.signal(signal.SIGINT, _inner)

    atexit.register(lambda: cleanup(ifindex, safe=True))


def setup_incoming(fn, ifindex):
    log.debug('Setup incoming hook (%s) (%s)', ifindex, fn.name)
    try:
        ipr.tc("add", "ingress", ifindex, "ffff:")
    except NetlinkError as exc:
        if exc.args[1] != 'File exists':
            raise

    action = {"kind": "bpf", "fd": fn.fd, "name": fn.name, "action": "ok"}
    ipr.tc(
        "add-filter", "u32", ifindex, ":1", parent="ffff:", action=[action],
        protocol=protocols.ETH_P_ALL, classid=1, target=0x10002, keys=['0x0/0x0+0'],
    )


def setup_outgoing(fn, ifindex):
    log.debug('Setup outgoing hook (%s) (%s)', ifindex, fn.name)

    try:
        ipr.tc("add", "sfq", ifindex, "1:")
    except NetlinkError as exc:
        if exc.args[1] != 'File exists':
            raise

    action = {"kind": "bpf", "fd": fn.fd, "name": fn.name, "action": "ok"}

    ipr.tc(
        "add-filter", "u32", ifindex, ":2", parent="1:", action=[action],
        protocol=protocols.ETH_P_ALL, classid=1, target=0x10002, keys=['0x0/0x0+0'],
    )

if __name__ == '__main__':
    main()