"""
BPF Operations

High-level composable operations that generate BPF code.
Similar to Django's migration operations.
"""

from typing import Optional, TYPE_CHECKING

from .elements import BPFStruct, BPFMap, BPFFunction

if TYPE_CHECKING:
    from .program import BPFProgram


class BPFOperation:
    """Base class for composable BPF operations

    Operations can add multiple elements (structs, maps, functions)
    to a BPF program in a composable, reusable way.
    """

    def apply(self, program: 'BPFProgram'):
        """Apply this operation to a BPF program

        Args:
            program: BPFProgram instance to modify
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement apply()")


class PacketRedirectOperation(BPFOperation):
    """Redirect packets from server_port to bind_port

    Ports the logic from sqredirect/redirect.c:
    - Incoming packets to server_port are redirected to bind_port
    - Outgoing packets from bind_port have source port rewritten to server_port
    - Supports both simple port-based and IP+port based lookup
    - Handles UDP checksum recalculation
    - Drops suspected DDoS packets (Steam protocol validation)

    Example:
        op = PacketRedirectOperation(
            server_port=27015,
            bind_port=27016,
            bind_ip="192.168.1.1"
        )
        program.apply_operation(op)
    """

    def __init__(
        self,
        server_port: int,
        bind_port: int,
        bind_ip: Optional[str] = None,
        use_ipport_key: bool = False
    ):
        """
        Args:
            server_port: Game server port to redirect from
            bind_port: Proxy bind port to redirect to
            bind_ip: Bind IP address (if None, uses port-only lookup)
            use_ipport_key: Use IP+port composite key instead of port-only.
                Note: If bind_ip is provided, use_ipport_key is automatically
                set to True regardless of the explicit value. To use port-only
                lookup, set bind_ip=None and use_ipport_key=False.
        """
        self.server_port = server_port
        self.bind_port = bind_port
        self.bind_ip = bind_ip
        # bind_ip presence takes precedence over explicit use_ipport_key
        self.use_ipport_key = use_ipport_key or (bind_ip is not None)

    def apply(self, program: 'BPFProgram'):
        """Apply packet redirect logic to program"""
        # Add required structs and maps
        if self.use_ipport_key:
            program.add_struct(BPFStruct("addr_key_t", [
                ("u32", "ip"),
                ("u16", "port")
            ]))
            program.add_map(BPFMap("addr_map", "struct addr_key_t", "u16", max_entries=1024))
        else:
            program.add_map(BPFMap("port_map", "u16", "u16", max_entries=1024))

        # Add incoming and outgoing functions
        program.add_function(self._create_incoming_function())
        program.add_function(self._create_outgoing_function())

    def _create_incoming_function(self) -> BPFFunction:
        """Port redirect.c incoming() function

        Handles packets arriving at the server port:
        1. Parse Ethernet/IP/UDP headers
        2. Validate packet structure and checksums
        3. Look up destination port in map
        4. Validate Steam protocol (DDoS protection)
        5. Redirect to bind port with checksum update
        """
        func = BPFFunction("incoming")

        # Parse packet headers
        func.add_code("""
    // Parse Ethernet header
    void *data_end = (void *)(long)skb->data_end;
    void *data = (void *)(long)skb->data;
    struct ethhdr *eth = data;

    if (data + sizeof(*eth) > data_end)
        return TC_ACT_OK;

    if (eth->h_proto != htons(ETH_P_IP))
        return TC_ACT_OK;

    // Parse IP header
    struct iphdr *iph = data + sizeof(*eth);
    if ((void *)(iph + 1) > data_end)
        return TC_ACT_OK;

    if (iph->protocol != IPPROTO_UDP)
        return TC_ACT_OK;

    // Parse UDP header
    struct udphdr *udph = (void *)iph + (iph->ihl * 4);
    if ((void *)(udph + 1) > data_end)
        return TC_ACT_OK;

    // Check UDP checksum (0 means no checksum)
    if (udph->check == 0)
        return TC_ACT_OK;
""")

        # Lookup logic (different for port-only vs IP+port)
        if self.use_ipport_key:
            func.add_code("""
    // Lookup using IP+port composite key
    struct addr_key_t key = {
        .ip = iph->daddr,
        .port = udph->dest
    };
    u16 *new_port = addr_map.lookup(&key);
    if (!new_port)
        return TC_ACT_OK;
""")
        else:
            func.add_code("""
    // Lookup using port-only key
    u16 dport = udph->dest;
    u16 *new_port = port_map.lookup(&dport);
    if (!new_port)
        return TC_ACT_OK;
""")

        # Steam protocol validation (DDoS protection)
        func.add_code("""
    // Validate Steam protocol packet
    void *payload = (void *)udph + sizeof(*udph);
    if (payload + 5 > data_end)
        return TC_ACT_OK;

    // Check for Steam protocol header (0xFFFFFFFF)
    u32 *header = payload;
    if (*header != 0xFFFFFFFF)
        return TC_ACT_SHOT;  // Drop non-Steam packets

    // Check packet type byte
    u8 *packet_type = payload + 4;
    // Valid types: A2S_INFO(0x54/'T'), A2S_PLAYER(0x55/'U'),
    //              A2S_RULES(0x56/'V'), A2A_PING(0x69/'i'),
    //              Challenge response(0x41/'A')
    if (*packet_type != 0x54 && *packet_type != 0x55 &&
        *packet_type != 0x56 && *packet_type != 0x69 &&
        *packet_type != 0x41)
        return TC_ACT_SHOT;  // Drop unknown packet types
""")

        # Redirect port with checksum update
        func.add_code("""
    // Store old port for checksum update
    u16 old_port = udph->dest;
    u16 new_port_val = htons(*new_port);

    // Update UDP checksum before modifying port
    // bpf_l4_csum_replace(skb, offset, from, to, flags)
    //   offset: offset to checksum field from skb->data
    //   from/to: old/new value (in network byte order)
    //   flags: size of value (2 for u16, 4 for u32)
    long csum_offset = (long)&udph->check - (long)skb->data;
    bpf_l4_csum_replace(skb, csum_offset, old_port, new_port_val, sizeof(u16));

    // Update UDP destination port
    udph->dest = new_port_val;

    return TC_ACT_OK;
""")

        return func

    def _create_outgoing_function(self) -> BPFFunction:
        """Port redirect.c outgoing() function

        Handles packets leaving the bind port:
        1. Parse Ethernet/IP/UDP headers
        2. Look up source port in map
        3. Rewrite source port back to server port
        4. Recalculate checksums
        """
        func = BPFFunction("outgoing")

        # Parse packet headers (same as incoming)
        func.add_code("""
    // Parse Ethernet header
    void *data_end = (void *)(long)skb->data_end;
    void *data = (void *)(long)skb->data;
    struct ethhdr *eth = data;

    if (data + sizeof(*eth) > data_end)
        return TC_ACT_OK;

    if (eth->h_proto != htons(ETH_P_IP))
        return TC_ACT_OK;

    // Parse IP header
    struct iphdr *iph = data + sizeof(*eth);
    if ((void *)(iph + 1) > data_end)
        return TC_ACT_OK;

    if (iph->protocol != IPPROTO_UDP)
        return TC_ACT_OK;

    // Parse UDP header
    struct udphdr *udph = (void *)iph + (iph->ihl * 4);
    if ((void *)(udph + 1) > data_end)
        return TC_ACT_OK;

    // Check UDP checksum
    if (udph->check == 0)
        return TC_ACT_OK;
""")

        # Lookup logic for outgoing (reverse of incoming)
        if self.use_ipport_key:
            func.add_code("""
    // Lookup using IP+port composite key
    struct addr_key_t key = {
        .ip = iph->saddr,
        .port = udph->source
    };
    u16 *original_port = addr_map.lookup(&key);
    if (!original_port)
        return TC_ACT_OK;
""")
        else:
            func.add_code("""
    // Lookup using port-only key
    u16 sport = udph->source;
    u16 *original_port = port_map.lookup(&sport);
    if (!original_port)
        return TC_ACT_OK;
""")

        # Rewrite source port with checksum update
        func.add_code("""
    // Store old port for checksum update
    u16 old_port = udph->source;
    u16 original_port_val = htons(*original_port);

    // Update UDP checksum before modifying port
    long csum_offset = (long)&udph->check - (long)skb->data;
    bpf_l4_csum_replace(skb, csum_offset, old_port, original_port_val, sizeof(u16));

    // Update UDP source port
    udph->source = original_port_val;

    return TC_ACT_OK;
""")

        return func
