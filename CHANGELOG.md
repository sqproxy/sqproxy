## v2.1.2 (2023-02-20)

### BREAKING CHANGE

- `values` subsection removed from `defaults`
section
- default error log path changed from /var/log/sqproxy/error.log to /dev/null, you need to set it manually now

### Feat

- **protocol**: support a2s_info with challenge number
- now src_query_port_lifetime ignored; Reconnect on each request
- **config**: support old-style config section - defaults.values
- **ebpf**: bind_ip now passed to sqredirect (v1.2.0 required) https://github.com/sqproxy/sqredirect/releases
- **config**: bind_ip/bind_port now optional and will be selected automatically
- **proxy**: allow ignore incoming client request by returning special object NO_RESPONSE
- **ebpf**: script_path now optional, respect running as sudo with custom executable
- **ebpf**: allow set executable as list, useful for 'sudo ...'
- **ebpf**: allow disable auto redirection; clarify server_port/bind_port options
- **logging**: now you can set logging level via SQPROXY_LOGLEVEL (default is INFO
- **proxy**: allow override default QueryProxy class implementation with your own
- **ebpf**: allow use '0.0.0.0' bind_ip with ebpf program (interpreted like default interface)
- **proxy**: allow disable a2s_rules request
- *****: start eBPF after got all responses from Game Server

### Fix

- **transport**: ignore udp errors on sending/receiving
- adapt to Py3.10 and Py3.11, no more deprecation warnings
- **deps**: support asyncio_dgram==2.*
- **logging**: no more ignoring loglevel
- **config**: we guarantee that the configuration files will be iterated by name in ascending order
- **config**: deep config merging
- **proxy**: no random stuck anymore
- **config**: fix typo `/etc/sqporxy` -> `/etc/sqproxy`
- **proxy**: no stuck if gameserver do not respond
- **logging**: logging setup as soon as possible; add sentry integration option; new SQPROXY_ERROR_LOG env

### Refactor

- **config**: defaults.global renamed into `defaults.__global__`
- **messages**: Message.encode don't require nosplit_header=True anymore. Now it's default.
- *****: pypi ready
