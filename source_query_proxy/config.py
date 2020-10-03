import importlib.util
import logging
import pathlib
import typing
from ipaddress import IPv4Address

import sentry_sdk
import yaml
from pydantic import AnyHttpUrl
from pydantic import BaseModel
from pydantic import BaseSettings
from pydantic import Extra
from pydantic import validator
from sentry_sdk.integrations.logging import LoggingIntegration

from . import __version__
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
)

logger = logging.getLogger('sqproxy.config')


class ConfigurationError(Exception):
    pass


class NetworkModel(BaseModel):
    server_ip: IPv4Address
    server_port: int
    bind_ip: IPv4Address
    bind_port: int
    ebpf_no_redirect: bool = False

    class Config:
        extra = Extra.forbid


class EntrypointModel(BaseModel):
    """Allow override proxy server entrypoint
    """

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
    a2s_info_cache_lifetime: int = 5
    a2s_rules_cache_lifetime: int = 5
    a2s_players_cache_lifetime: int = 1
    src_query_port_lifetime: int = 10
    no_a2s_rules: bool = False
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
    executable: str = 'python2'
    script_path: pathlib.Path = './src-ebpf/redirect.py'

    class Config:
        extra = Extra.forbid


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

    def get_merged_config_data(self):
        return load_configs(iter_config_files(self.confdir_0, self.confdir_1))

    @validator('loglevel')
    def _check_loglevel(cls, v):
        from logging import _checkLevel  # noqa

        _checkLevel(v)
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

            if config_defaults.get('global', False):
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


def setup(settings_: Settings = None):
    global settings
    if settings_ is None:
        logger.info('Re-read settings')
        settings_ = Settings()

    settings = settings_

    if settings.sentry_dsn:
        sentry_logging = LoggingIntegration(
            level=logging.DEBUG,  # Capture info and above as breadcrumbs
            event_level=logging.ERROR,  # Send errors as events
        )
        sentry_sdk.init(
            dsn=settings.sentry_dsn, integrations=[sentry_logging], release=__version__,
        )

    setup_logging(error_filename=settings.error_log.as_posix(),)

    if settings.sentry_dsn:
        logger.debug('Sentry enabled')
    else:
        logger.debug('Sentry disabled')

    merged_config_data = settings.get_merged_config_data()

    servers_ = merged_config_data.get('servers')
    if servers_:
        global servers
        servers = [(name, ServerModel.parse_obj(server)) for name, server in servers_.items()]

    ebpf_ = merged_config_data.get('ebpf')
    if ebpf_:
        global ebpf
        ebpf = EBPFModel.parse_obj(ebpf_)


settings = Settings()
servers = None  # type: typing.Optional[typing.List[typing.Tuple[str, ServerModel]]]
ebpf = None  # type: typing.Optional[EBPFModel]


setup(settings)
