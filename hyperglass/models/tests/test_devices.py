"""Test device configuration."""

# Standard Library
import typing as t
import unicodedata
from pathlib import Path

# Third Party
import pytest
from PIL import Image

# Project
from hyperglass.state import use_state
from hyperglass.settings import Settings
from hyperglass.models.directive import Directives
from hyperglass.exceptions.private import ConfigError, ConfigInvalid
from hyperglass.models.config.params import Params

# Local
from ..config.devices import Devices

if t.TYPE_CHECKING:
    # Project
    from hyperglass.state import HyperglassState


@pytest.fixture
def state() -> t.Generator["HyperglassState", None, None]:
    _state = use_state()
    with _state.cache.pipeline() as pipeline:
        pipeline.set("params", Params())
        pipeline.set(
            "directives",
            Directives.new(
                {"juniper_bgp_route": {"name": "BGP Route", "field": {"description": "test"}}}
            ),
        )
    yield _state
    _state.clear()


def _device(name: str, **kwargs: t.Any) -> t.Dict[str, t.Any]:
    return {
        "name": name,
        "address": "127.0.0.1",
        "credential": {"username": "", "password": ""},
        "platform": "juniper",
        "directives": ["juniper_bgp_route"],
        **kwargs,
    }


@pytest.mark.parametrize(
    "name,expected",
    (
        # IDs of ASCII names must never change, as they're used in URLs & caches.
        ("Example Device", "example_device"),
        ("Chicago, IL", "chicago_il"),
        ("NYC-1 (Equinix NY5)", "nyc-1_equinix_ny5"),
        ("  Lots   of  Space ", "lots_of_space"),
        ("Router_01.example.com", "router_01examplecom"),
        ("東京", "東京"),
        ("São Paulo", "são_paulo"),
        # Equivalent Unicode names produce the same ID.
        (unicodedata.normalize("NFD", "São Paulo"), "são_paulo"),
    ),
)
def test_device_id(state: "HyperglassState", name: str, expected: str):
    devices = Devices(_device(name))
    assert devices.ids == (expected,)
    assert devices[expected].name == name


def test_unique_unicode_ids(state: "HyperglassState"):
    devices = Devices(_device("東京"), _device("大阪"))
    assert set(devices.ids) == {"東京", "大阪"}


def test_duplicate_ids(state: "HyperglassState"):
    with pytest.raises(ConfigInvalid) as error:
        Devices(_device("Chicago, IL"), _device("Chicago IL"))
    assert "'Chicago IL'" in str(error.value)
    assert "'Chicago, IL'" in str(error.value)
    assert "chicago_il" in str(error.value)


def test_explicit_id(state: "HyperglassState"):
    devices = Devices(_device("Chicago, IL"), _device("Chicago IL", id="chicago_il_2"))
    assert devices.ids == ("chicago_il", "chicago_il_2")


def test_name_without_id_characters(state: "HyperglassState"):
    with pytest.raises(ValueError, match="Unable to generate an ID"):
        Devices(_device("!!!"))


def test_mask_attribute(state: "HyperglassState"):
    # Like `{target}`, `{mask}` is set from the query target, so it isn't a device attribute.
    command = "show ip route {target} {mask}"
    state.cache.set(
        "directives",
        Directives.new(
            {
                "ip_route": {
                    "name": "IP Route",
                    "rules": [{"condition": "0.0.0.0/0", "command": command}],
                    "field": {"description": "test"},
                }
            }
        ),
    )
    devices = Devices(_device("Router", directives=["ip_route"]))
    assert devices["router"].directive_commands == [command]


def test_proxy_unsupported_platform(state: "HyperglassState"):
    proxy = {"address": "127.0.0.1", "credential": {"username": "u", "password": "p"}}
    with pytest.raises(ConfigError, match="Proxies must use 'linux_ssh'"):
        Devices(_device("Router", proxy={**proxy, "platform": "cisco_ios"}))


def _avatar(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1024, 512), (200, 30, 30)).save(path)
    return path


def test_avatar_in_static_directory(
    state: "HyperglassState", monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(Settings, "app_path", tmp_path)
    avatar = _avatar(tmp_path / "static" / "images" / "nyc.png")
    original = avatar.read_bytes()

    devices = Devices(_device("NYC", avatar=avatar))

    assert devices["nyc"].avatar == avatar
    # The user's file is used as-is, and never modified.
    assert avatar.read_bytes() == original


def test_avatar_copied_and_resized(
    state: "HyperglassState", monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(Settings, "app_path", tmp_path / "app")
    avatar = _avatar(tmp_path / "avatars" / "nyc.png")
    original = avatar.read_bytes()

    Devices(_device("NYC", avatar=avatar))

    with Image.open(tmp_path / "app" / "static" / "images" / "nyc.png") as copied:
        assert copied.width == 512
    assert avatar.read_bytes() == original
