import logging
import pathlib
import typing
from ipaddress import IPv4Address

import yaml
from pydantic import BaseModel
from pydantic import BaseSettings
from pydantic import Extra
from pydantic import validator

from .dict_merge import dict_merge
from .logging import setup_logging

__all__ = (
    'NetworkModel',
    'ServerModel',
    'Settings',
    'ConfigurationError',
)

logger = logging.getLogger('sqproxy.config')


class ConfigurationError(Exception):
    pass


class NetworkModel(BaseModel):
    server_ip: IPv4Address
    server_port: int
    bind_ip: IPv4Address
    bind_port: int

    class Config:
        extra = Extra.forbid


class ServerModel(BaseModel):
    network: NetworkModel
    a2s_info_cache_lifetime: int = 5
    a2s_rules_cache_lifetime: int = 5
    a2s_players_cache_lifetime: int = 1
    src_query_port_lifetime: int = 10

    class Config:
        extra = Extra.forbid


class EBPFModel(BaseModel):
    enabled: bool = False
    executable: str = 'python2'
    script_path: pathlib.Path = './src-ebpf/redirect.py'

    class Config:
        extra = Extra.forbid


class Settings(BaseSettings):
    confdir_0: pathlib.Path = '/etc/sqporxy/conf.d/'
    confdir_1: pathlib.Path = './conf.d/'
    debug_log: pathlib.Path = '/var/log/sqproxy/debug.log'
    debug_log_enabled: bool = False
    piddir: typing.Optional[pathlib.Path] = None
    merged_config_data: dict = None

    class Config:
        env_file = '.env'
        env_prefix = 'SQPROXY_'

    @validator('merged_config_data')
    def merge_config_data(cls, v, values):  # noqa: ignore=N805
        assert v is None
        v = load_configs(iter_config_files(values['confdir_0'], values['confdir_1']))
        return v


def _apply_defaults(target, defaults):
    target.update(dict_merge(defaults, target))


def _get_config(data: dict, global_defaults) -> typing.Tuple[typing.Dict, typing.Dict]:
    """Get full and ready to use config
    """
    defaults = data.pop('defaults', None) or {}

    servers_data = data.get('servers')
    if not servers_data:
        return data, defaults

    for server in servers_data.values():
        for g_defaults in global_defaults:
            _apply_defaults(server, g_defaults['values'])

        if defaults and defaults.get('values'):
            _apply_defaults(server, defaults['values'])

    return data, defaults


def iter_config_files(*confdirs):
    for confdir in confdirs:
        if not confdir.exists():
            logger.info('Confdir not found: %s', confdir.absolute().as_posix())
            continue

        if not confdir.is_dir():
            logger.warning('Confdir expected to be a directory, not a file: %s', confdir.absolute().as_posix())
            continue

        for file in confdir.iterdir():
            if file.is_file() and file.name.endswith('.yaml'):
                logger.info('Found config: %s', file.as_posix())
                yield file


def load_configs(paths: typing.Iterable[pathlib.Path]):
    configs = []
    global_defaults = []

    ebpf_configured = False

    for path in paths:
        with path.open() as fp:
            config, config_defaults = _get_config(yaml.full_load(fp), global_defaults)

            if 'ebpf' in config:
                if ebpf_configured:
                    raise ConfigurationError('eBPF already configured')
                ebpf_configured = True

            if config_defaults.get('global', False):
                global_defaults.append(config_defaults)

            if config:
                configs.append(config)

    whole_config = {}
    for config in configs:
        whole_config.update(config)

    return whole_config


def setup(settings_: Settings = None):
    global settings
    if settings_ is None:
        logger.info('Re-read settings')
        settings_ = Settings()

    settings = settings_

    setup_logging(filename=settings.debug_log_enabled and settings.debug_log.as_posix() or None)

    servers_ = settings.merged_config_data.get('servers')
    if servers_:
        global servers
        servers = [(name, ServerModel.parse_obj(server)) for name, server in servers_.items()]

    ebpf_ = settings.merged_config_data.get('ebpf')
    if ebpf_:
        global ebpf
        ebpf = EBPFModel.parse_obj(ebpf_)


settings = Settings()
servers = None  # type: typing.Optional[typing.List[typing.Tuple[str, ServerModel]]]
ebpf = None  # type: typing.Optional[EBPFModel]


setup(settings)
