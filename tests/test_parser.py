import random
import time
from collections import defaultdict
from pathlib import Path
import numpy as np
import pytest
from readport import Item, Parser, ParseError


@pytest.mark.parametrize(
    "regex",
    [
        br"^.+,(?P<u>[^,]+),(?P<v>[^,]+),(?P<w>[^,]+),.,(?P<temp>[^,]+),.+$",
        br"^.+,(?P<u>[^,]+),(?P<v>[^,]+),(?P<w>[^,]+),.,(?P<temp>[^,]+),.+$"
        br"|(?P<extra>pattern)",  # a capture group that does not participate in a match
    ],
    ids=["regular", "non-capturing"],
)
def test_parser_extract(regex):
    """Check that well-formed inputs produce the correct extracted values
    """
    data = b"\x02Q,+000.079,-000.102,+000.095,M,+014.94,0000001,\x030F\r\n"
    timestamp = time.time()
    expected = dict(u=0.079, v=-0.102, w=0.095, temp=14.94, time=timestamp)

    item = Item(data, timestamp, False)
    parser = Parser(regex, 0, "")
    got = parser.extract(item)
    assert got == expected


def test_parser_extract_incomplete(caplog):
    """Ensure that an incomplete message results in no match and raises an exception
    """
    data = b"M,+014.94,0000001,\x030F\r\n"
    regex = br"^.+,(?P<u>[^,]+),(?P<v>[^,]+),(?P<w>[^,]+),.,(?P<temp>[^,]+),.+$"

    parser = Parser(regex, 0, "")
    with pytest.raises(ParseError):
        item = Item(data, time.time(), True)
        parser.extract(item)

    log = [
        rec.message
        for rec in caplog.records
        if "Possibly incomplete first message" in rec.message
    ]
    assert len(log) == 1

    with pytest.raises(ParseError):
        item = Item(data, time.time(), False)
        parser.extract(item)

    log = [
        rec.message
        for rec in caplog.records
        if "Cannot parse a complete message" in rec.message
    ]
    assert len(log) == 1


def test_parser_extract_cast_error():
    """Check that floating point conversions trigger an exception
    """
    data = b"\x02Q,ZZZ+000.079,-000.102,+000.095,M,+014.94,0000001,\x030F\r\n"
    regex = br"^.+,(?P<u>[^,]+),(?P<v>[^,]+),(?P<w>[^,]+),.,(?P<temp>[^,]+),.+$"

    item = Item(data, time.time(), False)
    parser = Parser(regex, 0, "")
    with pytest.raises(ParseError):
        parser.extract(item)


def test_parser_extract_duplicate_group():
    """Check that if regex is installed, the parser can extract a similar set of
    variables from two completely different string formats. Specifically, the same name
    can be used by more than one group.
    """
    pytest.importorskip("regex", reason="Please pip install regex")

    data = [
        b"01 RH= 1.23 %RH T= 14.94 'C \r\n",
        b"T= 11.83 'C RH= 1.35 %RH 02 \r\n",  # e.g. the variable order is reversed
    ]
    regex = (
        br"^(?P<level>\S+) RH= *(?P<rh>\S+) %RH T= *(?P<temp>\S+) .C\s*$"
        br"|^T= *(?P<temp>\S+) .C RH= *(?P<rh>\S+) %RH (?P<level>\S+)\s*$"
    )
    timestamp = time.time()
    expected = [
        dict(level=1.0, rh=1.23, temp=14.94, time=timestamp),
        dict(level=2.0, rh=1.35, temp=11.83, time=timestamp),
    ]

    for inp, exp in zip(data, expected):
        item = Item(inp, timestamp, False)
        parser = Parser(regex, 0, "")
        got = parser.extract(item)
        assert got == exp


def test_parser_write_ok(tmp_path):
    """Ensure that files are written properly
    """
    all_vars = ["u", "v", "w", "temp", "time"]
    pack_length = 2

    # Use microseconds and a unique file identifier
    dest = tmp_path / "data" / "MSU_Test1_{date:%H-%M-%S-%f}.npz"
    microsecond = 0.000001

    # Two complete files expected as output:
    n_iters = 2
    buffers = [defaultdict(list) for _ in range(n_iters)]

    parser = Parser(regex=b"", pack_length=pack_length, dest=dest)

    for i in range(n_iters):
        for _ in range(pack_length):
            variables = {var: random.uniform(-10, 10) for var in all_vars}
            parser.write(variables)

            # Form an expected representation of the data
            for var, value in variables.items():
                buffers[i][var].append(value)

        # Make sure that the whole iteration is at least 1 microsecond long
        time.sleep(microsecond)

    files = sorted([str(p) for p in tmp_path.glob("**/*") if p.is_file()])

    assert len(files) == n_iters
    for i, file in enumerate(files):
        with np.load(file) as data:
            for var in all_vars:
                expected = np.array(buffers[i][var])
                assert np.array_equal(data[var], expected)
                assert data[var].dtype == expected.dtype


def test_parser_write_inconsistent_vars(tmp_path):
    """Check that supplying a wrong set of variables triggers an exception
    """
    variables = {var: 1.0 for var in ["u", "v", "w", "time"]}

    pack_length = 2
    dest = tmp_path / "data" / "MSU_Test1_{date:%H-%M-%S-%f}.npz"

    parser = Parser(regex=b"", pack_length=pack_length, dest=dest)
    with pytest.raises(ParseError):
        parser.write(variables)
        # Remove one of the variables, which should cause an error
        del variables["u"]
        parser.write(variables)


def test_parser_write_mkdir_failed():
    """Test that failing at filesystem operations raises an error
    """
    variables = {var: 1.0 for var in ["u", "v", "w", "time"]}

    pack_length = 1
    # Use the /TEST directory to cause a permission problem
    dest = Path("/") / "TEST" / "MSU_Test1_{date:%H-%M-%S-%f}.npz"

    parser = Parser(regex=b"", pack_length=pack_length, dest=dest)
    with pytest.raises(ParseError):
        parser.write(variables)
