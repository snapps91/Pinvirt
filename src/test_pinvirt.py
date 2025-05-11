# test_pinvirt.py
"""
Unit-tests for pinvirt (compatible with Python 3.6).

The suite targets pure functions only; end-to-end CLI tests are omitted
because they depend on root privileges, real `lscpu` output and stdout
formatting that is better covered by integration tests.
"""
import json
import os
import tempfile
from typing import Dict, List, Set

import pytest

import pinvirt
from pinvirt import (
    LogicalCpu,
    CpuAllocationError,
    Errno,
    generate_cpu_allocation,
    build_ovirt_pinning_string,
    get_used_logical_cpus,
    get_cpu_topology,
    load_pinning,
    save_pinning,
    _normalize_legacy_command,
    _positive_int,
    require_root,
    remove_vm,
)

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_topology() -> List[LogicalCpu]:
    """
    Create a synthetic CPU topology:
      • 2 sockets
      • 2 physical cores per socket
      • Hyper-threading (2 logical CPUs per core)
    Logical IDs are chosen to match a typical x86 layout.
    """
    return [
        # Socket 0
        LogicalCpu(0, 0, 0), LogicalCpu(16, 0, 0),
        LogicalCpu(1, 1, 0), LogicalCpu(17, 1, 0),
        # Socket 1
        LogicalCpu(2, 0, 1), LogicalCpu(18, 0, 1),
        LogicalCpu(3, 1, 1), LogicalCpu(19, 1, 1),
    ]


@pytest.fixture
def pinning_file_tmp(tmp_path, monkeypatch):
    """
    Redirect pinvirt.PINNING_FILE to a temporary location for the duration
    of a test.
    """
    tmp_file = tmp_path / "pinning.json"
    monkeypatch.setattr(pinvirt, "PINNING_FILE", str(tmp_file))
    return tmp_file


# ---------------------------------------------------------------------------
# generate_cpu_allocation
# ---------------------------------------------------------------------------

def test_basic_allocation_one_thread(sample_topology):
    """Default policy: one logical per core on preferred socket."""
    result = generate_cpu_allocation(
        cpu_topology=sample_topology,
        num_vcpus=2,
        used_cpus=set(),
        target_socket=0,
        allow_multi_socket=False,
    )
    assert result == [0, 1]

def test_insufficient_physical_cores(sample_topology):
    # both threads of both cores on socket-0 are busy
    used = {0, 16, 1, 17}
    with pytest.raises(CpuAllocationError) as exc:
        generate_cpu_allocation(
            sample_topology, 2, used,
            target_socket=0, allow_multi_socket=False
        )
    assert exc.value.args[0] is Errno.INSUFFICIENT_CORES


def test_multi_socket_fallback(sample_topology):
    # no remaining cores on socket-0 → must fall back to socket-1
    used = {0, 16, 1, 17}
    result = generate_cpu_allocation(
        sample_topology, 2, used,
        target_socket=0, allow_multi_socket=True
    )
    assert result == [2, 3]      # first physical cores on socket-1


def test_hyperthread_strategy(sample_topology):
    """With use_hyperthreads=True the function must pack threads per core."""
    result = generate_cpu_allocation(
        sample_topology,
        3,
        set(),
        target_socket=0,
        allow_multi_socket=False,
        use_hyperthreads=True
    )
    # Expected order: 0,16 from core(0,0) then 1 from core(0,1)
    assert result == [0, 1, 16]


def test_invalid_socket_id(sample_topology):
    with pytest.raises(CpuAllocationError) as exc:
        generate_cpu_allocation(sample_topology, 1, set(), target_socket=99)
    assert exc.value.args[0] is Errno.NO_SOCKET


# ---------------------------------------------------------------------------
# build_ovirt_pinning_string
# ---------------------------------------------------------------------------

def test_build_ovirt_pinning_string():
    cpus = [7, 3, 1]
    assert build_ovirt_pinning_string(cpus) == "0#1_1#3_2#7"


# ---------------------------------------------------------------------------
# get_used_logical_cpus
# ---------------------------------------------------------------------------

def test_get_used_logical_cpus():
    mapping = {"vmA": [0, 1], "vmB": [4, 5]}
    assert get_used_logical_cpus(mapping) == {0, 1, 4, 5}


# ---------------------------------------------------------------------------
# get_cpu_topology – subprocess mocked
# ---------------------------------------------------------------------------

LSCPU_FAKE_OUTPUT = """\
# comment line ignored
0,0,0
16,0,0
1,1,0
17,1,0
"""

def test_get_cpu_topology_success(monkeypatch):
    monkeypatch.setattr(
        pinvirt.subprocess,
        "check_output",
        lambda *_, **__: LSCPU_FAKE_OUTPUT
    )
    topo = get_cpu_topology()
    assert topo == [
        LogicalCpu(0, 0, 0),
        LogicalCpu(16, 0, 0),
        LogicalCpu(1, 1, 0),
        LogicalCpu(17, 1, 0),
    ]


def test_get_cpu_topology_command_not_found(monkeypatch):
    def raise_fn(*_a, **_kw):
        raise FileNotFoundError
    monkeypatch.setattr(pinvirt.subprocess, "check_output", raise_fn)
    with pytest.raises(SystemExit):
        get_cpu_topology()


# ---------------------------------------------------------------------------
# load_pinning / save_pinning
# ---------------------------------------------------------------------------

def test_load_and_save_pinning(pinning_file_tmp):
    data_in = {"vmX": [1, 2, 3]}
    save_pinning(data_in)
    data_out = load_pinning()
    assert data_out == data_in


def test_load_pinning_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(pinvirt, "PINNING_FILE", str(tmp_path / "missing.json"))
    assert load_pinning() == {}


# ---------------------------------------------------------------------------
# helper utilities
# ---------------------------------------------------------------------------

def test_normalize_legacy_command():
    argv = ["pinvirt", "--add", "vm1", "2", "0"]
    assert _normalize_legacy_command(argv) == ["pinvirt", "add", "vm1", "2", "0"]


def test_positive_int_pass():
    assert _positive_int(10, "arg") == 10


def test_positive_int_fail():
    with pytest.raises(SystemExit):
        _positive_int(0, "arg")


def test_require_root_pass(monkeypatch):
    monkeypatch.setattr(pinvirt.os, "geteuid", lambda: 0)
    require_root()  # should *not* raise


def test_require_root_fail(monkeypatch):
    monkeypatch.setattr(pinvirt.os, "geteuid", lambda: 1000)
    with pytest.raises(SystemExit):
        require_root()


# ---------------------------------------------------------------------------
# remove_vm
# ---------------------------------------------------------------------------

def test_remove_vm(pinning_file_tmp, capsys):
    pinning = {"vmY": [0, 1]}
    save_pinning(pinning)
    remove_vm("vmY", pinning)
    out, _ = capsys.readouterr()
    assert "Removed" in out
    assert "vmY" not in pinning
