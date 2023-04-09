import importlib.util
import logging
import pathlib
import typing
from ipaddress import IPv4Address

import sentry_sdk
import yaml
from cached_property import cached_property
from pydantic import AnyHttpUrl
from pydantic import BaseModel
from pydantic import BaseSettings
from pydantic import Extra
from pydantic import confloat
from pydantic import conint
from pydantic import validator
from sentry_sdk.integrations.logging import LoggingIntegration

from . import __version__
from . import utils
from .dict_merge import dict_merge
from .logging import setup_logging

if typing.TYPE_CHECKING:
    from .proxy import QueryProxy

    QueryProxyType = typing.TypeVar('QueryProxyType', bound=QueryProxy)
else:
    QueryProxyType = None


__all__ = (
    'NetworkModel',
    'ServerModel',
    'Settings',
    'ConfigurationError',
    'settings',
)

logger = logging.getLogger('sqproxy.config')


class ConfigurationError(Exception):
    pass


class NetworkModel(BaseModel):
    server_ip: IPv4Address
    server_port: conint(ge=1, le=65535)
    bind_ip: typing.Optional[IPv4Address] = None
    bind_port: typing.Optional[conint(ge=0, le=65535)] = 0
    ebpf_no_redirect: bool = False

    class Config:
        extra = Extra.forbid

    @validator('bind_ip', always=True)
    def _set_default_bind_ip(cls, bind_ip, values):
        if not bind_ip:
            bind_ip = values['server_ip']

        return bind_ip

    @validator('bind_port', always=True)
    def _set_default_bind_port(cls, bind_port, values):
        if bind_port is None or bind_port == 0:
            server_port = values['server_port']

            if utils.is_port_available(server_port + 800):
                # try to use pretty port
                bind_port = server_port + 800
            else:
                bind_port = utils.get_available_port()

        return bind_port


class EntrypointModel(BaseModel):
    """Allow override proxy server entrypoint"""

    path: str  #: path to callable which should return :class:`QueryProxy`-based object
    obj: typing.Optional[typing.Callable[..., QueryProxyType]] = None

    class Config:
        extra = Extra.forbid

    @validator('obj', always=True)
    def _import_obj(cls, v, values):
        if v is not None:
            return v

        path: str = values['path']
        if ':' not in path:
            raise ValueError(f'entry not found, expected path(s): example.py:MyObj, example:MyObj. Given: {path}')

        file_path, _, attr_name = path.rpartition(':')

        if not file_path.isidentifier():
            file_path = pathlib.Path(file_path).resolve()
            spec = importlib.util.spec_from_file_location('entrypoint', file_path)
            module = importlib.util.module_from_spec(spec)
            module.__loader__.exec_module(module)  # noqa
        else:
            module = importlib.import_module(file_path)

        try:
            return getattr(module, attr_name)
        except AttributeError as exc:
            raise AttributeError(exc.args[0].replace("'entrypoint'", f"'{file_path}'"))


class ServerModel(BaseModel):
    meta: dict
    network: NetworkModel
    a2s_info_cache_lifetime: confloat(gt=0) = 5
    a2s_rules_cache_lifetime: confloat(gt=0) = 5
    a2s_players_cache_lifetime: confloat(gt=0) = 1
    a2s_response_timeout: confloat(gt=0) = 1
    no_a2s_rules: bool = False
    wait_ready_graceful_period: confloat(gt=0) = 5
    max_a2s_fails_before_offline: conint(gt=0) = 10
    entrypoint: typing.Optional[EntrypointModel] = None

    @validator('entrypoint', pre=True)
    def _entrypoint(cls, v, values):
        if isinstance(v, str):
            v = {'path': v}

        v['path'] = v['path'].format_map(values['meta'])
        return v

    class Config:
        extra = Extra.allow


class EBPFModel(BaseModel):
    enabled: bool = False
    executable: typing.Union[str, typing.List[str]] = 'python2'
    script_path: typing.Optional[pathlib.Path] = None

    class Config:
        extra = Extra.forbid


NamedServersType = typing.List[typing.Tuple[str, ServerModel]]


class Settings(BaseSettings):
    sentry_dsn: typing.Optional[AnyHttpUrl] = None
    confdir_0: pathlib.Path = '/etc/sqproxy/conf.d/'
    confdir_1: pathlib.Path = './conf.d/'
    error_log: pathlib.Path = '/dev/null'
    loglevel: str = 'INFO'
    piddir: typing.Optional[pathlib.Path] = None

    class Config:
        env_file = '.env'
        env_prefix = 'SQPROXY_'
        keep_untouched = (cached_property,)

    @cached_property
    def merged_config_data(self):
        return load_configs(iter_config_files(self.confdir_0, self.confdir_1))

    @validator('loglevel')
    def _check_loglevel(cls, v):
        from logging import _checkLevel  # noqa

        _checkLevel(v)
        return v

    @cached_property
    def servers(self) -> NamedServersType:
        merged_config_data = self.merged_config_data

        servers = merged_config_data.get('servers')
        if servers:
            servers = [(name, ServerModel.parse_obj(server)) for name, server in servers.items()]

        return servers or []

    @cached_property
    def ebpf(self) -> typing.Optional[EBPFModel]:
        ebpf = self.merged_config_data.get('ebpf')
        if not ebpf:
            return None
        return EBPFModel.parse_obj(ebpf)


def _apply_defaults(target, defaults):
    target.update(dict_merge(defaults, target))


def _get_old_config(data: dict, global_defaults) -> typing.Tuple[typing.Dict, typing.Dict]:
    """Get full and ready to use config"""
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


def _get_config(data: dict, global_defaults) -> typing.Tuple[typing.Dict, typing.Dict]:
    """Get full and ready to use config"""
    if 'global' in (data.get('defaults') or {}):
        data, defaults = _get_old_config(data, global_defaults)
        is_global = defaults.pop('global')
        defaults = defaults['values']
        defaults['__global__'] = is_global
        return data, defaults

    defaults = data.pop('defaults', None) or {}

    servers_data = data.get('servers')
    if not servers_data:
        return data, defaults

    for server in servers_data.values():
        for g_defaults in global_defaults:
            _apply_defaults(server, g_defaults)

        if defaults:
            _apply_defaults(server, defaults)

    return data, defaults


def iter_config_files(*confdirs):
    for confdir in confdirs:
        if not confdir.exists():
            logger.info('Confdir not found: %s', confdir.absolute().as_posix())
            continue

        if not confdir.is_dir():
            logger.warning('Confdir expected to be a directory, not a file: %s', confdir.absolute().as_posix())
            continue

        for file in sorted(confdir.iterdir(), key=lambda f: f.name):
            if file.is_file() and file.name.endswith('.yaml'):
                logger.info('Found config: %s', file.as_posix())
                yield file
            else:
                logger.debug('Found non-config file, ignore: %s', file.as_posix())


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

            if config_defaults.pop('__global__', False):
                global_defaults.append(config_defaults)

            if config:
                meta = {'CONFPATH': path, 'CONFDIR': path.parent}
                for server in (config.get('servers') or {}).values():
                    server['meta'] = meta

                configs.append(config)

    whole_config = {}
    for config in configs:
        whole_config = dict_merge(whole_config, config)

    return whole_config


def setup(settings_: Settings = None, reread: bool = False):
    global settings
    if settings_ is None or reread:
        logger.info('Re-read settings')
        settings_ = Settings()

    settings = settings_

    if settings.sentry_dsn:
        sentry_logging = LoggingIntegration(
            level=logging.DEBUG,  # Capture info and above as breadcrumbs
            event_level=logging.ERROR,  # Send errors as events
        )
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            integrations=[sentry_logging],
            release=__version__,
        )

    setup_logging(loglevel=settings.loglevel, error_filename=settings.error_log.as_posix())

    if settings.sentry_dsn:
        logger.debug('Sentry enabled')
    else:
        logger.debug('Sentry disabled')

    return settings


settings = Settings()

setup(settings)


def __getattr__(name):
    if name == 'ebpf':
        return settings.ebpf
    elif name == 'servers':
        return settings.servers
    else:
        raise AttributeError(name)
