#!/usr/bin/env python3
"""
================================================================================
Pinvirt
================================================================================

Description:
  A Python utility to automate and manage CPU core assignments (pinning)
  for Virtual Machines (VMs) on Linux hosts. It retrieves the CPU topology
  using 'lscpu', tracks VM-to-CPU mappings in a local JSON database,
  and generates oVirt-compatible CPU pinning strings.

Features:
  - Automatic or manual CPU allocation for VMs
  - Multi-socket and hyper-threading support
  - Display of host CPU topology and available logical CPUs
  - Persistent storage of pinning assignments
  - Easy removal of VM entries

Requirements:
  - Python 3.x
  - 'lscpu' command available on the system

Usage:
  Run the script with the desired command:
   pinvirt --help

Author:
  Giacomo Failla - 2025 <giacomo.failla@cheope.io>

License:
  MIT License

================================================================================
"""


import argparse
import json
import logging
import os
import subprocess
import sys
from enum import IntEnum
from typing import Dict, List, NamedTuple, Set, Tuple

PinningMap = Dict[str, List[int]]
CpuInfo = List[Tuple[int, int, int]]  # (logical_cpu, core_id, socket_id)

PINNING_FILE = "/etc/pinvirt/cpu_pinning_map.json"


class CpuAllocationError(RuntimeError):
    """Errore nel calcolo del pinning CPU."""


class Errno(IntEnum):
    NO_SOCKET = 1
    INSUFFICIENT_CORES = 2


class LogicalCpu(NamedTuple):
    logical_id: int
    core_id: int
    socket_id: int


def load_pinning() -> PinningMap:
    """Loads the CPU pinning data from the local JSON file."""
    if not os.path.exists(PINNING_FILE):
        return {}
    try:
        with open(PINNING_FILE) as file:
            return json.load(file)
    except json.JSONDecodeError:
        print(f"[ERROR] Could not decode {PINNING_FILE}. Assuming empty.")
        return {}
    except OSError as e:
        print(f"[ERROR] Could not read {PINNING_FILE}: {e}")
        return {}


def save_pinning(data: PinningMap) -> None:
    """Saves the current CPU pinning data to the local JSON file."""
    try:
        with open(PINNING_FILE, "w") as file:
            json.dump(data, file, indent=2)
    except OSError as e:
        print(f"[ERROR] Could not write to {PINNING_FILE}: {e}")
        sys.exit(1)


def get_cpu_topology() -> CpuInfo:
    """Retrieves the CPU topology of the host system using `lscpu`."""
    try:
        output = subprocess.check_output(
            ["lscpu", "-p=CPU,CORE,SOCKET"], universal_newlines=True
        )
    except FileNotFoundError:
        print(
            "[ERROR] `lscpu` command not found. Please ensure it's installed and in PATH."
        )
        sys.exit(1)
    except subprocess.SubprocessError as e:
        print(f"[ERROR] Failed to run lscpu: {e}")
        sys.exit(1)

    topology: CpuInfo = []
    parsed_cpus = set()

    for line in output.splitlines():
        if line.startswith("#"):
            continue
        parts = line.strip().split(",")
        if len(parts) == 3:
            try:
                logical_cpu, core_id, socket_id = map(int, parts)
                if logical_cpu not in parsed_cpus:  # evita duplicati
                    topology.append(LogicalCpu(logical_cpu, core_id, socket_id))
                    parsed_cpus.add(logical_cpu)
            except ValueError:
                print(f"[WARN] Skipping invalid line in lscpu output: {line}")

    if not topology:
        print("[ERROR] Could not parse any CPU topology information from lscpu.")
        sys.exit(1)

    return topology


def get_used_logical_cpus(pinning_data: PinningMap) -> Set[int]:
    """Extracts the set of all logical CPUs currently assigned to VMs."""
    used: Set[int] = set()
    for cpu_list in pinning_data.values():
        used.update(cpu_list)
    return used


def generate_cpu_allocation(
    cpu_topology,  # Iterable[LogicalCpu]
    num_vcpus,  # int
    used_cpus,  # Set[int]
    target_socket=None,  # Optional[int]
    allow_multi_socket=False,  # bool
    use_hyperthreads=False,  # bool
):
    available_sockets = {cpu.socket_id for cpu in cpu_topology}
    if (target_socket is not None) and (target_socket not in available_sockets):
        logging.error(
            "Socket %s inesistente. Disponibili: %s",
            target_socket,
            sorted(available_sockets),
        )
        raise CpuAllocationError(Errno.NO_SOCKET)

    available_cores = {}  # type: Dict[Tuple[int, int], List[int]]

    for cpu in cpu_topology:
        if cpu.logical_id in used_cpus:
            continue
        if (
            target_socket is not None
            and not allow_multi_socket
            and cpu.socket_id != target_socket
        ):
            continue

        key = (cpu.socket_id, cpu.core_id)
        available_cores.setdefault(key, []).append(cpu.logical_id)

    for ids in available_cores.values():
        ids.sort()

    def core_sort_key(item):
        (socket_id, core_id), _ = item
        preferred = target_socket is not None and socket_id == target_socket
        return (0 if preferred else 1, socket_id, core_id)

    sorted_core_groups = sorted(available_cores.items(), key=core_sort_key)

    assigned = []  # type: List[int]

    if not use_hyperthreads:
        single_threads = [cpus[0] for _, cpus in sorted_core_groups]
        if len(single_threads) < num_vcpus:
            logging.error(
                "Insufficient physical cores: required %s, available %s",
                num_vcpus,
                len(single_threads),
            )
            raise CpuAllocationError(Errno.INSUFFICIENT_CORES)
        assigned = single_threads[:num_vcpus]
    else:
        total_logical = sum(len(cpus) for cpus in available_cores.values())
        if total_logical < num_vcpus:
            logging.error(
                "Insufficient logical cpu: requests %s, available %s",
                num_vcpus,
                total_logical,
            )
            raise CpuAllocationError(Errno.INSUFFICIENT_CORES)

        for _, cpus in sorted_core_groups:
            need = num_vcpus - len(assigned)
            if need <= 0:
                break
            assigned.extend(cpus[:need])

    return sorted(assigned)


def build_ovirt_pinning_string(assigned_cpus: List[int]) -> str:
    """Formats a list of logical CPUs into a pinning string compatible with oVirt."""
    # Ensure input is sorted for consistent oVirt string if order doesn't matter
    sorted_cpus = sorted(assigned_cpus)
    return "_".join(f"{v_cpu}#{p_cpu}" for v_cpu, p_cpu in enumerate(sorted_cpus))


def list_vms(pinning_data: PinningMap) -> None:
    print("\n📋 Currently pinned VMs:")
    if not pinning_data:
        print("  (none)")
        return

    for vm_name, cpus in sorted(pinning_data.items()):
        # Ensure CPUs are sorted before generating the string for consistency
        sorted_cpus = sorted(cpus)
        ovirt_string: str = build_ovirt_pinning_string(sorted_cpus)
        print(f"  🖥️  {vm_name}")
        print(f"      • CPUs assigned  : {sorted_cpus}")
        print(f"      • oVirt pinning  : {ovirt_string}")
    print()


def list_available_cpus(cpu_topology: CpuInfo, used_cpus: Set[int]) -> None:
    all_logical_cpus: Set[int] = {cpu for cpu, _, _ in cpu_topology}
    available: List[int] = sorted(list(all_logical_cpus - used_cpus))
    print(f"\n🧠 Available logical CPUs ({len(available)}):")
    print(f"  {available}\n")


def remove_vm(vm_name: str, pinning_data: PinningMap) -> None:
    if vm_name not in pinning_data:
        print(f"[WARN] VM '{vm_name}' not found in pinning records.")
        return
    del pinning_data[vm_name]
    save_pinning(pinning_data)
    print(f"[INFO] Removed pinning entry for VM '{vm_name}'.")


def print_cpu_topology(cpu_topology: CpuInfo, used_cpus: Set[int]) -> None:
    print("\n Host CPU Topology (Logical CPUs per Physical Core)")
    print(
        " Status: ✅ = Core fully available | ❌ = Core partially/fully used | * = CPU assigned"
    )
    print("-------------------------------------------------------------")

    topology_map: Dict[int, Dict[int, List[int]]] = {}
    all_logical_cpus: Set[int] = set()

    for logical_cpu, core_id, socket_id in cpu_topology:
        topology_map.setdefault(socket_id, {}).setdefault(core_id, []).append(
            logical_cpu
        )
        all_logical_cpus.add(logical_cpu)

    for socket_id in sorted(topology_map):
        print(f"Socket {socket_id}:")
        for core_id in sorted(topology_map[socket_id]):
            logicals = sorted(topology_map[socket_id][core_id])
            core_used = any(cpu in used_cpus for cpu in logicals)
            status = "❌" if core_used else "✅"
            cpu_strs = []
            for cpu in logicals:
                marker = "*" if cpu in used_cpus else " "
                cpu_strs.append(f"{cpu:3d}{marker}")

            cpu_str = "][".join(cpu_strs)
            print(f"  Core {core_id:3d}: [{cpu_str}] {status}")
        print()


# ---------------------------------------------------------------------------
# Backwards‑compatibility layer
# ---------------------------------------------------------------------------

LEGACY_COMMANDS = {
    "--add": "add",
    "--add-manual": "add-manual",
    "--remove": "remove",
    "--list": "list",
    "--topology": "topology",
    "--free-cpus": "free-cpus",
    "--help": "help",
}


def _normalize_legacy_command(argv: List[str]) -> List[str]:
    """Translate legacy ``--command`` style into sub‑commands.

    The transformation is *idempotent* and affects only the *first*
    argument after the executable name so that paths like ``--version``
    (if ever added) remain untouched.
    """
    if len(argv) > 1 and argv[1] in LEGACY_COMMANDS:
        argv = argv[:1] + [LEGACY_COMMANDS[argv[1]]] + argv[2:]
    return argv


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def require_root() -> None:
    """Abort execution if the current user is not *root*."""
    if os.geteuid() != 0:
        sys.exit("[ERROR] This script must be run as root.")


def _positive_int(value: int, param_name: str) -> int:
    """Ensure *value* is strictly positive, otherwise exit with error."""
    if value <= 0:
        sys.exit(f"[ERROR] {param_name} must be a positive integer.")
    return value


# ---------------------------------------------------------------------------
# Argument‑parser construction
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pinvirt",
        description=("Manage vCPU pinning for virtual machines.\n\n"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="<command>",
        help="Run 'pinvirt <command> --help' for details.",
    )

    # ---------------------------- add (automatic) --------------------------
    add_parser = subparsers.add_parser(
        "add",
        help="Automatically pin a new VM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_parser.add_argument("vm_name", help="Name of the virtual machine.")
    add_parser.add_argument("num_vcpus", type=int, help="Number of vCPUs.")
    add_parser.add_argument("socket_id", type=int, help="Preferred socket ID.")
    add_parser.add_argument(
        "--multi-socket",
        action="store_true",
        help="Allow using cores from any socket if needed.",
    )
    add_parser.add_argument(
        "--use-ht",
        action="store_true",
        help="Use both hyper‑threads of each core before moving to the next.",
    )

    # ------------------------- add‑manual (manual) -------------------------
    add_manual_parser = subparsers.add_parser(
        "add-manual", help="Manually pin a VM to a list of logical CPUs."
    )
    add_manual_parser.add_argument("vm_name", help="Name of the VM.")
    add_manual_parser.add_argument(
        "cpu_list",
        help="Comma‑separated list of logical CPU IDs (e.g. '1,3,5,7').",
    )

    # ------------------------------ remove ---------------------------------
    remove_parser = subparsers.add_parser(
        "remove", help="Remove a VM's pinning record."
    )
    remove_parser.add_argument("vm_name", help="Name of the VM.")

    # ------------------------ simple information ---------------------------
    subparsers.add_parser("list", help="List all pinned VMs.")
    subparsers.add_parser("topology", help="Show host CPU topology.")
    subparsers.add_parser("free-cpus", help="Show logical CPUs not assigned to any VM.")
    subparsers.add_parser("help", help="Show this help message and exit.")

    return parser


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _handle_add(args: argparse.Namespace, pinning_data: "PinningMap") -> None:
    _positive_int(args.num_vcpus, "num_vcpus")

    vm_name = args.vm_name
    if vm_name in pinning_data:
        sys.exit(
            "[ERROR] VM '{}' is already pinned. Run 'remove' first to re‑pin.".format(
                vm_name
            )
        )

    cpu_topology = get_cpu_topology()
    used_cpus = get_used_logical_cpus(pinning_data)

    assigned_cpus = generate_cpu_allocation(
        cpu_topology=cpu_topology,
        num_vcpus=args.num_vcpus,
        used_cpus=used_cpus,
        target_socket=args.socket_id,
        allow_multi_socket=args.multi_socket,
        use_hyperthreads=args.use_ht,
    )

    pinning_data[vm_name] = assigned_cpus
    save_pinning(pinning_data)

    strategy_msg = "using hyper‑threads" if args.use_ht else "using one thread per core"
    print(
        "\n✅  Automatically pinned VM '{}' with {} vCPU(s) ({})".format(
            vm_name, args.num_vcpus, strategy_msg
        )
    )
    print("   Assigned logical CPUs:", assigned_cpus)
    print("------------------------------------------------")
    print("oVirt pinning string:")
    print(build_ovirt_pinning_string(assigned_cpus))
    print("------------------------------------------------\n")


def _handle_add_manual(args: argparse.Namespace, pinning_data: "PinningMap") -> None:
    vm_name = args.vm_name
    if vm_name in pinning_data:
        sys.exit(
            "[ERROR] VM '{}' is already pinned. Run 'remove' first to re‑pin.".format(
                vm_name
            )
        )

    # Parse and validate the CPU list
    try:
        assigned_cpus = sorted(
            int(cpu.strip()) for cpu in args.cpu_list.split(",") if cpu.strip()
        )
    except ValueError:
        sys.exit(f"[ERROR] Invalid CPU list '{args.cpu_list}'. Expected integers.")

    if not assigned_cpus:
        sys.exit("[ERROR] CPU list cannot be empty.")
    if len(assigned_cpus) != len(set(assigned_cpus)):
        sys.exit("[ERROR] Duplicate CPU IDs detected in the list.")

    cpu_topology = get_cpu_topology()
    all_system_cpus = {cpu for cpu, _, _ in cpu_topology}
    used_cpus = get_used_logical_cpus(pinning_data)

    invalid_cpus = {cpu for cpu in assigned_cpus if cpu not in all_system_cpus}
    conflicting_cpus = {cpu for cpu in assigned_cpus if cpu in used_cpus}

    if invalid_cpus or conflicting_cpus:
        print("[ERROR] Cannot add VM pinning due to validation errors:")
        if invalid_cpus:
            print("  - Non‑existent CPU IDs:", sorted(invalid_cpus))
        if conflicting_cpus:
            print("  - CPUs already in use:", sorted(conflicting_cpus))
        list_available_cpus(cpu_topology, used_cpus)
        sys.exit(1)

    pinning_data[vm_name] = assigned_cpus
    save_pinning(pinning_data)

    print(f"\n✅  Manually pinned VM '{vm_name}'")
    print("   Assigned logical CPUs:", assigned_cpus)
    print("------------------------------------------------")
    print("oVirt pinning string:")
    print(build_ovirt_pinning_string(assigned_cpus))
    print("------------------------------------------------\n")


def _handle_remove(args: argparse.Namespace, pinning_data: "PinningMap") -> None:
    remove_vm(args.vm_name, pinning_data)


def _handle_simple(
    command: str, cpu_topology: "CpuInfo", pinning_data: "PinningMap"
) -> None:
    used_cpus = get_used_logical_cpus(pinning_data)

    if command == "list":
        list_vms(pinning_data)
    elif command == "free-cpus":
        list_available_cpus(cpu_topology, used_cpus)
    elif command == "topology":
        print_cpu_topology(cpu_topology, used_cpus)
    else:  # pragma: no cover – should never happen
        sys.exit(f"[BUG] Unhandled simple command: {command}")


# ---------------------------------------------------------------------------
# Main entry‑point
# ---------------------------------------------------------------------------


def main() -> None:
    argv = _normalize_legacy_command(sys.argv)
    parser = _build_parser()

    # No sub‑command provided → show usage and exit.
    if len(argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    # ``argparse`` <3.7 lacks required=True for sub‑parsers; manual check.
    args = parser.parse_args(argv[1:])
    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        sys.exit(1)

    # The fake "help" sub‑command is kept solely for backward compatibility.
    if args.command == "help":
        parser.print_help()
        return

    require_root()

    # Shared state loaded once per invocation
    pinning_data = load_pinning()
    cpu_topology = get_cpu_topology()

    if args.command == "add":
        _handle_add(args, pinning_data)
    elif args.command == "add-manual":
        _handle_add_manual(args, pinning_data)
    elif args.command == "remove":
        _handle_remove(args, pinning_data)
    else:
        _handle_simple(args.command, cpu_topology, pinning_data)


if __name__ == "__main__":  # pragma: no cover
    main()
