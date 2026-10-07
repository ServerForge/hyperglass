"""Test configuration validation."""

# Standard Library
import typing as t
from pathlib import Path

# Third Party
import yaml
import pytest

# Project
from hyperglass.state import use_state
from hyperglass.settings import Settings
from hyperglass.models.directive import Directives
from hyperglass.exceptions.private import ConfigError, ConfigInvalid

# Local
from ..validate import init_params, init_devices, init_ui_params, init_directives

if t.TYPE_CHECKING:
    # Project
    from hyperglass.state import HyperglassState

DEVICE = """
  - name: {name}
    address: 127.0.0.1
    credential: {{username: test, password: test}}
    platform: juniper
    directives: [juniper_bgp_route]
"""


@pytest.fixture
def app_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(Settings, "app_path", tmp_path)
    return tmp_path


@pytest.fixture
def state() -> t.Generator["HyperglassState", None, None]:
    _state = use_state()
    _state.cache.set(
        "directives",
        Directives.new(
            {"juniper_bgp_route": {"name": "BGP Route", "field": {"description": "test"}}}
        ),
    )
    yield _state
    _state.clear()


@pytest.mark.parametrize(
    "config,location,message",
    (
        ("- a\n- b\n", "config.yaml", "Expected a mapping of configuration parameters"),
        ("web:\n  theme:\n    colors:\n      cyan: nope\n", "cyan", "not a valid color"),
        ("web:\n  dns_provider: google\n", "dns_provider", "Expected a mapping"),
        ("web:\n  dns_provider:\n    name: quad9\n", "dns_provider", "'quad9' is not"),
        ("web:\n  logo:\n    width: 150%\n", "width", "Invalid size"),
        (
            "org_name: A Very Long Organization Name, Inc.\n"
            "web:\n  text:\n    subtitle: '{org_name} LG'\n",
            "subtitle",
            "at most 32",
        ),
    ),
)
def test_invalid_params(app_path: Path, config: str, location: str, message: str):
    (app_path / "config.yaml").write_text(config)
    with pytest.raises(ConfigInvalid) as error:
        init_params()
    assert location in str(error.value)
    assert message in str(error.value)


def test_text_placeholders(app_path: Path):
    """Only known placeholders are replaced, other text with braces is kept as-is."""
    greeting = app_path / "greeting.md"
    greeting.write_text('# {title}\nExample JSON: {} and {"a": 1} :-}')
    menu = 'By using {site_title}: `policy X { term 1 { then accept; } }` {"location": "x"}'
    config = {
        "primary_asn": 65000,
        "site_description": "AS{primary_asn} {org_name} {unknown}",
        "web": {
            "text": {"subtitle": "AS{primary_asn} :-}"},
            "links": [
                {"title": "PeeringDB", "url": "https://www.peeringdb.com/asn/{primary_asn}"},
                {"title": "Status", "url": "https://status.example.com/{org}?asn={primary_asn}"},
            ],
            "menus": [{"title": "Help", "content": menu}],
            "greeting": {"enable": True, "title": "Welcome", "file": str(greeting)},
        },
    }
    (app_path / "config.yaml").write_text(yaml.safe_dump(config))

    params = init_params()

    assert params.site_description == "AS65000 Beloved Hyperglass User {unknown}"
    assert params.web.text.subtitle == "AS65000 :-}"
    assert [str(link.url) for link in params.web.links] == [
        "https://www.peeringdb.com/asn/65000",
        "https://status.example.com/%7Borg%7D?asn=65000",
    ]
    assert params.web.menus[0].content == menu.replace("{site_title}", "hyperglass")
    ui_params = init_ui_params(params=params, devices=_no_devices())
    assert ui_params.content.greeting == '# Welcome\nExample JSON: {} and {"a": 1} :-}'


def _no_devices():
    # Project
    from hyperglass.models.config.devices import Devices

    return Devices()


@pytest.mark.parametrize(
    "directives,location,message",
    (
        ("- name: foo\n", "directives.yaml", "Expected a mapping of directive IDs"),
        ("foo: bar\n", "foo", "Expected a mapping of directive parameters"),
        (
            "foo:\n  name: Foo\n  rules:\n    - condition: 0.0.0.0/0\n      action: maybe\n",
            "directives.yaml → foo → rules → action",
            "Input should be 'permit' or 'deny'",
        ),
    ),
)
def test_invalid_directives(app_path: Path, directives: str, location: str, message: str):
    (app_path / "directives.yaml").write_text(directives)
    with pytest.raises(ConfigInvalid) as error:
        init_directives()
    assert location in str(error.value)
    assert message in str(error.value)


@pytest.mark.parametrize(
    "devices,exception,message",
    (
        ("- name: router1\n", ConfigInvalid, "Expected a mapping with a 'devices' key"),
        ("devices:\n", ConfigError, "No devices are defined in devices.yaml"),
        ("devices: []\n", ConfigError, "No devices are defined in devices.yaml"),
        ("devices:\n  name: router1\n", ConfigInvalid, "Expected a list of devices"),
        ("devices:\n  - router1\n", ConfigInvalid, "Expected a mapping of device parameters"),
        (
            "devices:\n  - address: 127.0.0.1\n    platform: juniper\n",
            ConfigInvalid,
            "devices.yaml → devices → 0\n  Error: name is required",
        ),
        (
            "devices:" + DEVICE.format(name="router1").replace("127.0.0.1", "[1, 2]"),
            ConfigInvalid,
            "devices.yaml → devices → router1 → address",
        ),
        (
            "devices:" + DEVICE.format(name="'Chicago, IL'") + DEVICE.format(name="Chicago IL"),
            ConfigInvalid,
            "Device 'Chicago IL' has the same ID ('chicago_il') as device 'Chicago, IL'",
        ),
    ),
)
def test_invalid_devices(
    app_path: Path,
    state: "HyperglassState",
    devices: str,
    exception: t.Type[Exception],
    message: str,
):
    (app_path / "devices.yaml").write_text(devices)
    with pytest.raises(exception) as error:
        init_devices()
    assert message in str(error.value)


def test_devices(app_path: Path, state: "HyperglassState"):
    (app_path / "devices.yaml").write_text(
        "devices:" + DEVICE.format(name="東京") + DEVICE.format(name="大阪")
    )
    devices = init_devices()
    assert set(devices.ids) == {"東京", "大阪"}
