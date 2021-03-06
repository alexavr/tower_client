import configparser
import importlib
from io import StringIO
import pytest
import readport
from readport import Group, load_config, ConfigurationError


def test_load_config():
    """Check that the loaded configuration options have correct values and data types"""
    config = r"""
        [device]
        station = MSU
        name = Test
        host = 127.0.0.1
        port = 4001
        timeout = 30

        [parser]
        regex = ^(?P<level>\S+) RH= *(?P<rh>\S+) %RH T= *(?P<temp>\S+) .C\s*$
        group_by = level:int
        pack_length = 12000
        destination = ./data/

        [logging]
        level = DEBUG
        file = readport_${device:port}.log
    """

    with StringIO(config) as f:
        conf = load_config(f)

    assert conf.station == "MSU"
    assert conf.device == "Test"
    assert conf.host == "127.0.0.1"
    assert conf.port == 4001
    assert conf.timeout == 30
    assert (
        conf.regex == br"^(?P<level>\S+) RH= *(?P<rh>\S+) %RH T= *(?P<temp>\S+) .C\s*$"
    )
    assert conf.group == Group(by="level", dtype="int")
    assert conf.pack_length == 12000
    assert conf.dest_dir == "./data/"
    assert conf.log_level == "DEBUG"
    assert conf.log_file == "readport_4001.log"


def test_missing_setting():
    """Ensure that missing required options trigger an exception"""

    config = r"""
        [device]

        [parser]

        [logging]
    """
    with StringIO(config) as f:
        with pytest.raises(configparser.NoOptionError):
            load_config(f)


def test_config_no_timeout():
    """Check that a commented out "timeout" yields timeout=None."""
    config = r"""
        [device]
        station = MSU
        name = Test
        host = 127.0.0.1
        port = 4001
        #timeout = 30

        [parser]
        regex = ^x= *(?P<u>\S+) y= *(?P<v>\S+) z= *(?P<w>\S+) T= *(?P<temp>\S+).*$
        pack_length = 12000
        destination = ./data/

        [logging]
        level = DEBUG
        file = readport_${device:port}.log
    """

    with StringIO(config) as f:
        conf = load_config(f)

    assert conf.timeout is None


@pytest.mark.parametrize(
    "regex",
    [
        # The reserved variable name "time" mustn't be used:
        r"^x= *(?P<u>\S+) y= *(?P<v>\S+) z= *(?P<w>\S+) T= *(?P<time>\S+).*$",
        # Regex must be valid (e.g. no missing braces):
        r"^x= *(?P<u>\S+) y= *(?P<v>\S+) z= *(?P<w>\S+) T= *(?P<temp>\S+.*$",
        # All capture groups must be named:
        r"^x= *(?P<u>\S+) y= *(?P<v>\S+) z= *(?P<w>\S+) T= *(\S+).*$",
    ],
    ids=["reserved variable", "invalid regex", "unnamed groups"],
)
def test_regex_error(regex):
    """Check that issues with the regex trigger an exception"""
    config = r"""
        [device]
        station = MSU
        name = Test
        host = 127.0.0.1
        port = 4001
        timeout = 30

        [parser]
        regex = {regex}
        pack_length = 12000
        destination = ./data/

        [logging]
        level = DEBUG
        file = readport_${{device:port}}.log
    """

    with StringIO(config.format(regex=regex)) as f:
        with pytest.raises(ConfigurationError):
            load_config(f)


def test_regex_no_advanced():
    """Test that advanced regex functionality, particularly capture groups with
    the same name:
        - raise an error if `regex` isn't installed
    """
    config = r"""
        [device]
        station = MSU
        name = Test
        host = 127.0.0.1
        port = 4001
        timeout = 30

        [parser]
        regex = (?P<name>foo)|(?P<name>bar)
        pack_length = 12000
        destination = ./data/

        [logging]
        level = DEBUG
        file = readport_${device:port}.log
    """
    readport.re = importlib.import_module("re")
    with StringIO(config) as f:
        with pytest.raises(ConfigurationError):
            load_config(f)


def test_regex_advanced():
    """Test that advanced regex functionality, particularly capture groups with
    the same name:
        - pass the configuration check if `regex` is installed
    """
    config = r"""
        [device]
        station = MSU
        name = Test
        host = 127.0.0.1
        port = 4001
        timeout = 30

        [parser]
        regex = (?P<name>foo)|(?P<name>bar)
        pack_length = 12000
        destination = ./data/

        [logging]
        level = DEBUG
        file = readport_${device:port}.log
    """
    pytest.importorskip("regex", reason="For this test: pip install regex")

    readport.re = importlib.import_module("regex")
    with StringIO(config) as f:
        load_config(f)  # no exception should be raised


def test_missing_group_by():
    """Ensure that if group_by isn't specified, the loaded values are Nones"""
    config = r"""
        [device]
        station = MSU
        name = Test
        host = 127.0.0.1
        port = 4001
        timeout = 30

        [parser]
        regex = ^(?P<level>\S+) RH= *(?P<rh>\S+) %RH T= *(?P<temp>\S+) .C\s*$
        # group_by = 
        pack_length = 12000
        destination = ./data/

        [logging]
        level = DEBUG
        file = readport_${device:port}.log
    """
    with StringIO(config) as f:
        conf = load_config(f)

    assert conf.group == Group()


@pytest.mark.parametrize(
    "group_by",
    [
        # if provided, group_by must be in the format <variable>:<type>
        "level",
        # if group_by is provided, the data type must also be specified
        "level:",
        # group_by must be set to one of the named capture groups from the regex
        "something_else:int",
        # the data type must be set to one of the allowed values
        "level:object",
    ],
    ids=["incorrect format", "missing type", "unknown variable", "unknown type"],
)
def test_group_by_errors(group_by):
    """Ensure that if group_by is specified, it is correctly formatted"""
    config = r"""
            [device]
            station = MSU
            name = Test
            host = 127.0.0.1
            port = 4001
            timeout = 30

            [parser]
            regex = ^(?P<level>\S+) RH= *(?P<rh>\S+) %RH T= *(?P<temp>\S+) .C\s*$
            group_by = {group_by}
            pack_length = 12000
            destination = ./data/

            [logging]
            level = DEBUG
            file = readport_${{device:port}}.log
        """
    with StringIO(config.format(group_by=group_by)) as f:
        with pytest.raises(ConfigurationError):
            load_config(f)
