## v2.2.0 (2023-04-02)

### Feat

- make i/o more stable
- support new uvloop + python 3.11

## v2.1.2 (2023-02-20)

### Fix

- **transport**: ignore udp errors on sending/receiving

## v2.1.1 (2021-12-18)

### Fix

- adapt to Py3.10 and Py3.11, no more deprecation warnings
- **deps**: support asyncio_dgram==2.*

## v2.1.0 (2021-06-19)

### Feat

- **protocol**: support a2s_info with challenge number
- now src_query_port_lifetime ignored; Reconnect on each request

## v2.0.0 (2021-03-28)

### BREAKING CHANGE

- `values` subsection removed from `defaults`
section

### Feat

- **config**: support old-style config section - defaults.values
- **ebpf**: bind_ip now passed to sqredirect (v1.2.0 required) https://github.com/sqproxy/sqredirect/releases
- **config**: bind_ip/bind_port now optional and will be selected automatically

### Refactor

- **config**: defaults.global renamed into `defaults.__global__`

## v1.4.0 (2020-10-04)

### Feat

- **proxy**: allow ignore incoming client request by returning special object NO_RESPONSE

## v1.3.1 (2020-10-04)

### Fix

- **logging**: no more ignoring loglevel

## v1.3.0 (2020-10-03)

### Feat

- **ebpf**: script_path now optional, respect running as sudo with custom executable
- **ebpf**: allow set executable as list, useful for 'sudo ...'

## v1.2.0 (2020-10-03)

### BREAKING CHANGE

- default error log path changed from /var/log/sqproxy/error.log to /dev/null, you need to set it manually now

### Feat

- **ebpf**: allow disable auto redirection; clarify server_port/bind_port options
- **logging**: now you can set logging level via SQPROXY_LOGLEVEL (default is INFO
- **proxy**: allow override default QueryProxy class implementation with your own
- **ebpf**: allow use '0.0.0.0' bind_ip with ebpf program (interpreted like default interface)

## v1.1.2 (2020-07-31)

### Fix

- **config**: we guarantee that the configuration files will be iterated by name in ascending order
- **config**: deep config merging

## v1.1.1 (2020-06-17)

### Fix

- **proxy**: no random stuck anymore

## v1.1.0 (2020-04-17)

### Feat

- **proxy**: allow disable a2s_rules request
- *****: start eBPF after got all responses from Game Server

### Fix

- **config**: fix typo `/etc/sqporxy` -> `/etc/sqproxy`
- **proxy**: no stuck if gameserver do not respond

## v1.0.1 (2020-04-14)

### Fix

- **logging**: logging setup as soon as possible; add sentry integration option; new SQPROXY_ERROR_LOG env

## v1.0.0 (2020-03-16)

### Refactor

- **messages**: Message.encode don't require nosplit_header=True anymore. Now it's default.
- *****: pypi ready
