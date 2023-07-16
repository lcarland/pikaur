"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import configparser
import os
import random
import sys
from abc import ABCMeta, abstractmethod
from pathlib import Path
from tempfile import gettempdir
from typing import TYPE_CHECKING

from .i18n import PIKAUR_NAME, translate

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any, Final

    from typing_extensions import NotRequired, TypedDict

    class DeprecatedConfigValue(TypedDict):
        section: str
        option: str
        transform: NotRequired[Callable[[str, configparser.ConfigParser], str]]

    class ConfigValueType(TypedDict):
        data_type: str
        default: NotRequired[str]
        deprecated: NotRequired[DeprecatedConfigValue]
        migrated: NotRequired[bool]


class IntOrBoolSingleton:

    value: int

    @classmethod
    def set_value(cls, value: int) -> None:
        cls.value = value

    @classmethod
    def init_value(cls) -> int:
        return 0

    @classmethod
    def get_value(cls) -> int:
        if getattr(cls, "value", None) is None:
            cls.value = cls.init_value()
        return cls.value

    def __call__(self) -> int:
        return self.get_value()


# class StringSingleton:

#     value: str

#     @classmethod
#     def set_value(cls, value: str) -> None:
#         cls.value = value

#     @classmethod
#     def init_value(cls) -> str:
#         return ""

#     @classmethod
#     def get_value(cls) -> str:
#         if getattr(cls, "value", None) is None:
#             cls.value = cls.init_value()
#         return cls.value

#     def __call__(self) -> str:
#         return self.get_value()


class PathSingleton(metaclass=ABCMeta):

    value: Path

    @classmethod
    def set_value(cls, value: Path) -> None:
        cls.value = value

    @classmethod
    @abstractmethod
    def get_value(cls) -> Path:
        pass

    def __call__(self) -> Path:
        return self.get_value()


class FixedPathSingleton(PathSingleton):

    @classmethod
    @abstractmethod
    def init_value(cls) -> Path:
        pass

    @classmethod
    def get_value(cls) -> Path:
        if getattr(cls, "value", None) is None:
            cls.value = cls.init_value()
        return cls.value


VERSION: "Final" = "1.16.1-dev"

DEFAULT_CONFIG_ENCODING: "Final" = "utf-8"
BOOL: "Final" = "bool"
INT: "Final" = "int"
STR: "Final" = "str"


class CustomUserId(IntOrBoolSingleton):
    @classmethod
    def init_value(cls) -> int:
        return (
            [
                int(arg.split("=", maxsplit=1)[1])
                for arg in sys.argv
                if arg.startswith("--user-id")
            ]
            or [0]
        )[0]


class RunningAsRoot(IntOrBoolSingleton):
    @classmethod
    def init_value(cls) -> int:
        return os.geteuid() == 0


def update_custom_user_id(new_id: int) -> None:
    CustomUserId.set_value(CustomUserId()() or new_id)


class UsingDynamicUsers(IntOrBoolSingleton):
    @classmethod
    def get_value(cls) -> int:
        return RunningAsRoot()() and not CustomUserId()()


class Home(PathSingleton):
    @classmethod
    def get_value(cls) -> Path:
        return (
            Path(os.environ["HOME"])
            if (RunningAsRoot()() and CustomUserId()())
            else Path.home()
        )


class _UserTempRoot(FixedPathSingleton):
    @classmethod
    def init_value(cls) -> Path:
        return Path(gettempdir())


class _UserCacheRoot(PathSingleton):
    @classmethod
    def get_value(cls) -> Path:
        return Path(os.environ.get(
            "XDG_CACHE_HOME",
            Home()() / ".cache/",
        ))


class CacheRoot(PathSingleton):
    @classmethod
    def get_value(cls) -> Path:
        return (
            Path("/var/cache/pikaur")
            if UsingDynamicUsers()() else
            _UserCacheRoot()() / "pikaur/"
        )


BUILD_CACHE_PATH: "Final" = CacheRoot()() / "build"
PACKAGE_CACHE_PATH: "Final" = CacheRoot()() / "pkg"

CONFIG_ROOT: "Final" = Path(os.environ.get(
    "XDG_CONFIG_HOME",
    Home()() / ".config/",
))

DATA_ROOT: "Final" = (
    Path(os.environ.get(
        "XDG_DATA_HOME",
        Home()() / ".local/share/",
    )) / "pikaur"
)

_OLD_AUR_REPOS_CACHE_PATH: "Final" = CacheRoot()() / "aur_repos"
AUR_REPOS_CACHE_PATH: "Final" = (
    (CacheRoot()() / "aur_repos")
    if UsingDynamicUsers()() else
    (DATA_ROOT / "aur_repos")
)

BUILD_DEPS_LOCK: "Final" = (
    (
        _UserCacheRoot()() if UsingDynamicUsers()() else _UserTempRoot()())
    / "pikaur_build_deps.lock"
)
PROMPT_LOCK: "Final" = (
    (
        _UserCacheRoot()() if UsingDynamicUsers()() else _UserTempRoot()()
    ) / f"pikaur_prompt_{random.randint(0, 999999)}.lock"  # nosec: B311   # noqa: S311
)


def get_config_path() -> Path:
    config_flag = "--pikaur-config"
    if config_flag in sys.argv:
        return Path(sys.argv[
            sys.argv.index(config_flag) + 1
        ])
    return CONFIG_ROOT / "pikaur.conf"


class UpgradeSortingValues:
    VERSIONDIFF: "Final" = "versiondiff"
    PKGNAME: "Final" = "pkgname"
    REPO: "Final" = "repo"


class AurSearchSortingValues:
    HOTTEST: "Final" = "hottest"
    PKGNAME: "Final" = "pkgname"
    POPULARITY: "Final" = "popularity"
    NUMVOTES: "Final" = "numvotes"
    LASTMODIFIED: "Final" = "lastmodified"


class DiffPagerValues:
    AUTO: "Final" = "auto"
    ALWAYS: "Final" = "always"
    NEVER: "Final" = "never"


CONFIG_YES_VALUES: "Final" = ("yes", "y", "true", "1")


ConfigSchemaT = dict[str, dict[str, "ConfigValueType"]]
CONFIG_SCHEMA: ConfigSchemaT = {
    "sync": {
        "AlwaysShowPkgOrigin": {
            "data_type": BOOL,
            "default": "no",
        },
        "DevelPkgsExpiration": {
            "data_type": INT,
            "default": "-1",
        },
        "UpgradeSorting": {
            "data_type": STR,
            "default": UpgradeSortingValues.VERSIONDIFF,
        },
        "ShowDownloadSize": {
            "data_type": BOOL,
            "default": "no",
        },
        "IgnoreOutofdateAURUpgrades": {
            "data_type": BOOL,
            "default": "no",
        },
    },
    "build": {
        "KeepBuildDir": {
            "data_type": BOOL,
            "default": "no",
        },
        "KeepDevBuildDir": {
            "data_type": BOOL,
            "default": "yes",
        },
        "KeepBuildDeps": {
            "data_type": BOOL,
            "default": "no",
        },
        "GpgDir": {
            "data_type": STR,
            "default": ("/etc/pacman.d/gnupg/" if RunningAsRoot()() else ""),
        },
        "SkipFailedBuild": {
            "data_type": BOOL,
            "default": "no",
        },
        "DynamicUsers": {
            "data_type": STR,
            "default": "root",
        },
        "AlwaysUseDynamicUsers": {
            "data_type": BOOL,
            "default": "no",
            "deprecated": {
                "section": "build",
                "option": "DynamicUsers",
                "transform": lambda old_value, _config: "always" if old_value == "yes" else "root",
            },
        },
        "NoEdit": {
            "data_type": BOOL,
            "deprecated": {
                "section": "review",
                "option": "NoEdit",
            },
        },
        "DontEditByDefault": {
            "data_type": BOOL,
            "deprecated": {
                "section": "review",
                "option": "DontEditByDefault",
            },
        },
        "NoDiff": {
            "data_type": BOOL,
            "deprecated": {
                "section": "review",
                "option": "NoDiff",
            },
        },
        "GitDiffArgs": {
            "data_type": STR,
            "deprecated": {
                "section": "review",
                "option": "GitDiffArgs",
            },
        },
        "IgnoreArch": {
            "data_type": BOOL,
            "default": "no",
        },
    },
    "review": {
        "NoEdit": {
            "data_type": BOOL,
            "default": "no",
        },
        "DontEditByDefault": {
            "data_type": BOOL,
            "default": "no",
        },
        "NoDiff": {
            "data_type": BOOL,
            "default": "no",
        },
        "GitDiffArgs": {
            "data_type": STR,
            "default": "--ignore-space-change,--ignore-all-space",
        },
        "DiffPager": {
            "data_type": STR,
            "default": DiffPagerValues.AUTO,
        },
        "HideDiffFiles": {
            "data_type": STR,
            "default": ".SRCINFO",
        },
    },
    "colors": {
        "Version": {
            "data_type": INT,
            "default": "10",
        },
        "VersionDiffOld": {
            "data_type": INT,
            "default": "11",
        },
        "VersionDiffNew": {
            "data_type": INT,
            "default": "9",
        },
    },
    "ui": {
        "RequireEnterConfirm": {
            "data_type": BOOL,
            "default": "yes",
        },
        "DiffPager": {
            "data_type": STR,
            "deprecated": {
                "section": "review",
                "option": "DiffPager",
            },
        },
        "PrintCommands": {
            "data_type": BOOL,
            "default": "no",
        },
        "AurSearchSorting": {
            "data_type": STR,
            "default": AurSearchSortingValues.HOTTEST,
        },
        "DisplayLastUpdated": {
            "data_type": BOOL,
            "default": "no",
        },
        "GroupByRepository": {
            "data_type": BOOL,
            "default": "yes",
        },
        "ReverseSearchSorting": {
            "data_type": BOOL,
            "default": "no",
        },
        "WarnAboutPackageUpdates": {
            "data_type": STR,
            "default": "",
        },
    },
    "misc": {
        "AurHost": {
            "data_type": STR,
            "deprecated": {
                "section": "network",
                "option": "AurUrl",
                "transform": lambda old_value, _config: f"https://{old_value}",
            },
        },
        "NewsUrl": {
            "data_type": STR,
            "deprecated": {
                "section": "network",
                "option": "NewsUrl",
            },
        },
        "PacmanPath": {
            "data_type": STR,
            "default": "pacman",
        },
        "PrivilegeEscalationTool": {
            "data_type": STR,
            "default": "sudo",
        },
        "PrivilegeEscalationTarget": {
            "data_type": STR,
            "default": "pikaur",
        },
        "UserId": {
            "data_type": INT,
            "default": "0",
        },
    },
    "network": {
        "AurUrl": {
            "data_type": STR,
            "default": "https://aur.archlinux.org",
        },
        "NewsUrl": {
            "data_type": STR,
            "default": "https://www.archlinux.org/feeds/news/",
        },
        "Socks5Proxy": {
            "data_type": STR,
            "default": "",
        },
        "AurHttpProxy": {
            "data_type": STR,
            "default": "",
        },
        "AurHttpsProxy": {
            "data_type": STR,
            "default": "",
        },
    },
}


def get_key_type(section_name: str, key_name: str) -> str | None:
    config_value: "ConfigValueType" | None = CONFIG_SCHEMA.get(section_name, {}).get(key_name, None)
    if not config_value:
        return None
    return config_value.get("data_type")


def write_config(config: configparser.ConfigParser | None = None) -> None:
    if not config:
        config = configparser.ConfigParser()
    need_write = False
    for section_name, section in CONFIG_SCHEMA.items():
        if section_name not in config:
            config[section_name] = {}
        for option_name, option_schema in section.items():
            if option_schema.get("migrated"):
                need_write = True
                continue
            if option_schema.get("deprecated"):
                continue
            if option_name not in config[section_name]:
                config[section_name][option_name] = option_schema["default"]
                need_write = True
    if need_write:
        update_custom_user_id(int(config["misc"]["UserId"]))
        if not CONFIG_ROOT.exists():
            CONFIG_ROOT.mkdir(parents=True)
        with get_config_path().open("w", encoding=DEFAULT_CONFIG_ENCODING) as configfile:
            config.write(configfile)
        if custom_user_id := CustomUserId()():
            for path in (
                CONFIG_ROOT,
                get_config_path(),
            ):
                os.chown(path, custom_user_id, custom_user_id)


def str_to_bool(value: str) -> bool:
    return value.lower() in CONFIG_YES_VALUES


class PikaurConfigItem:

    def __init__(self, section: configparser.SectionProxy, key: str) -> None:
        self.section = section
        self.key = key
        self.value = self.section.get(key)
        self._type_error_template = translate(
            "{key} is not '{typeof}'",
        )

    def get_bool(self) -> bool:
        if get_key_type(self.section.name, self.key) != BOOL:
            not_bool_error = self._type_error_template.format(key=self.key, typeof=BOOL)
            raise TypeError(not_bool_error)
        return str_to_bool(self.value)

    def get_int(self) -> int:
        if get_key_type(self.section.name, self.key) != INT:
            not_int_error = self._type_error_template.format(key=self.key, typeof=INT)
            raise TypeError(not_int_error)
        return int(self.value)

    def get_str(self) -> str:
        # note: it"s basically needed for mypy
        if get_key_type(self.section.name, self.key) != STR:
            not_str_error = self._type_error_template.format(key=self.key, typeof=STR)
            raise TypeError(not_str_error)
        return str(self.value)

    def __str__(self) -> str:
        return self.get_str()

    def __eq__(self, item: "Any") -> bool:
        result: bool = self.get_str() == item
        return result


class PikaurConfigSection:

    section: configparser.SectionProxy

    def __init__(self, section: configparser.SectionProxy) -> None:
        self.section = section

    def __getattr__(self, attr: str) -> PikaurConfigItem:
        return PikaurConfigItem(self.section, attr)

    def __repr__(self) -> str:
        return str(self.section)


class PikaurConfig:

    _config: configparser.ConfigParser

    @classmethod
    def get_config(cls) -> configparser.ConfigParser:
        if not getattr(cls, "_config", None):
            config_path = get_config_path()
            cls._config = configparser.ConfigParser()
            if not config_path.exists():
                write_config()
            cls._config.read(config_path, encoding=DEFAULT_CONFIG_ENCODING)
            cls.migrate_config()
            write_config(config=cls._config)
            cls.validate_config()
            update_custom_user_id(int(cls._config["misc"]["UserId"]))
        return cls._config

    @classmethod
    def migrate_config(cls) -> None:
        for section_name, section in CONFIG_SCHEMA.items():
            for option_name, option_schema in section.items():
                if not option_schema.get("deprecated"):
                    continue

                new_section_name: str = option_schema["deprecated"]["section"]
                new_option_name: str = option_schema["deprecated"]["option"]
                transform: """Callable[
                    [str, configparser.ConfigParser], str,
                ] | None""" = option_schema["deprecated"].get("transform")

                old_value_was_migrated = False
                value_to_migrate = None
                if (
                        new_section_name not in cls._config
                ) or (
                    cls._config[new_section_name].get(new_option_name) is None
                ):
                    value_to_migrate = cls._config[section_name].get(option_name)
                    if value_to_migrate is not None:
                        if transform:
                            new_value = transform(value_to_migrate, cls._config)
                        else:
                            new_value = value_to_migrate
                        if new_section_name not in cls._config:
                            cls._config[new_section_name] = {}
                        cls._config[new_section_name][new_option_name] = new_value
                        CONFIG_SCHEMA[new_section_name][new_option_name]["migrated"] = True
                        old_value_was_migrated = True

                old_value_was_removed = False
                if option_name in cls._config[section_name]:
                    del cls._config[section_name][option_name]
                    CONFIG_SCHEMA[section_name][option_name]["migrated"] = True
                    old_value_was_removed = True

                if old_value_was_migrated or old_value_was_removed:
                    print(" ".join([  # noqa: T201
                        "::",
                        translate("warning:"),
                        translate('Migrating [{}]{}="{}" config option to [{}]{}="{}"...').format(
                            section_name, option_name,
                            value_to_migrate or "",
                            new_section_name, new_option_name,
                            cls._config[new_section_name][new_option_name],
                        ),
                        "\n",
                    ]))

    @classmethod
    def validate_config(cls) -> None:
        pacman_path = cls._config["misc"]["PacmanPath"]
        if pacman_path in (PIKAUR_NAME, sys.argv[0]) or pacman_path.endswith(f"/{PIKAUR_NAME}"):
            print("BAM! I am a shell bomb.")  # noqa: T201
            sys.exit(1)

    def __getattr__(self, attr: str) -> PikaurConfigSection:
        return PikaurConfigSection(self.get_config()[attr])
