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
    python3 pin_manager.py --help

Author:
  Giacomo Failla - 2025 <giacomo.failla@cheope.io>

License:
  MIT License

================================================================================
"""

from __future__ import annotations

import subprocess
import sys
import json
import os
from typing import List, Tuple, Dict, Set, Optional
import argparse

PinningMap = Dict[str, List[int]]
CpuInfo = List[Tuple[int, int, int]]  # (logical_cpu, core_id, socket_id)

PINNING_FILE = "/etc/pinvirt/cpu_pinning_map.json"


def load_pinning() -> PinningMap:
    """Loads the CPU pinning data from the local JSON file."""
    if not os.path.exists(PINNING_FILE):
        return {}
    try:
        with open(PINNING_FILE, "r") as file:
            return json.load(file)
    except json.JSONDecodeError:
        print(f"[ERROR] Could not decode {PINNING_FILE}. Assuming empty.")
        return {}
    except IOError as e:
        print(f"[ERROR] Could not read {PINNING_FILE}: {e}")
        return {}


def save_pinning(data: PinningMap) -> None:
    """Saves the current CPU pinning data to the local JSON file."""
    try:
        with open(PINNING_FILE, "w") as file:
            json.dump(data, file, indent=2)
    except IOError as e:
        print(f"[ERROR] Could not write to {PINNING_FILE}: {e}")
        sys.exit(1)


def get_cpu_topology() -> CpuInfo:
    """Retrieves the CPU topology of the host system using `lscpu`."""
    try:
        output: str = subprocess.check_output(
            ["lscpu", "-p=CPU,CORE,SOCKET"], universal_newlines=True
        )
    except FileNotFoundError:
        print("[ERROR] `lscpu` command not found. Please ensure it's installed and in PATH.")
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
                # Avoid duplicate entries if lscpu output is strange
                if logical_cpu not in parsed_cpus:
                    topology.append((logical_cpu, core_id, socket_id))
                    parsed_cpus.add(logical_cpu)
            except ValueError:
                print(f"[WARN] Skipping invalid line in lscpu output: {line}")
                continue
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
    cpu_topology: CpuInfo,
    num_vcpus: int,
    used_cpus: Set[int],
    target_socket: Optional[int] = None,
    allow_multi_socket: bool = False,
    use_ht: bool = False, # <-- Nuovo parametro
) -> List[int]:
    """
    Allocates a list of available logical CPUs for vCPU pinning (AUTOMATIC MODE).

    Args:
        cpu_topology: List of tuples (logical_cpu, core_id, socket_id).
        num_vcpus: Number of vCPUs requested for the VM.
        used_cpus: Set of logical CPUs already in use.
        target_socket: Optional socket ID to prefer (defaults to None).
        allow_multi_socket: If True, allows using CPUs from any socket.
        use_hyperthreads: If True, assign all threads from a core before
                          moving to the next. If False (default), assign only
                          one thread per core.

    Returns:
        A list of logical CPU IDs to assign to vCPUs.

    Raises:
        SystemExit: If not enough CPUs/cores are available or target socket is invalid.
    """
    available_sockets = {socket_id for _, _, socket_id in cpu_topology}
    if target_socket is not None and target_socket not in available_sockets:
        print(f"[ERROR] Target socket {target_socket} does not exist. Available: {sorted(list(available_sockets))}")
        sys.exit(1)

    # --- Build map of available CPUs, grouped by core ---
    # Dict[Tuple[socket_id, core_id], List[logical_cpu]]
    available_cores: Dict[Tuple[int, int], List[int]] = {}
    total_available_logical_cpus = 0

    for logical_cpu, core_id, socket_id in cpu_topology:
        # Filter by target socket if specified and multi-socket not allowed
        if target_socket is not None and not allow_multi_socket and socket_id != target_socket:
            continue
        # Skip already used CPUs
        if logical_cpu in used_cpus:
            continue

        core_key = (socket_id, core_id)
        if core_key not in available_cores:
            available_cores[core_key] = []
        available_cores[core_key].append(logical_cpu)
        total_available_logical_cpus += 1

    # Sort logical CPUs within each core's list for predictable order
    for core_key in available_cores:
        available_cores[core_key].sort()

    # Convert to a list of tuples: [((socket, core), [cpus]), ...]
    # and sort primarily by preferred socket (if specified), then socket, then core
    def sort_key(item):
        (socket_id, core_id), _ = item
        is_preferred = (target_socket is not None and socket_id == target_socket)
        # Sort preferred socket first (0), others later (1)
        # Then sort by socket_id, then core_id
        return (0 if is_preferred else 1, socket_id, core_id)

    sorted_core_groups = sorted(available_cores.items(), key=sort_key)

    # --- Select CPUs based on the chosen strategy ---
    assigned_cpus: List[int] = []

    if not use_ht:
        # Strategy 1: One logical CPU per physical core (Original Behavior)
        available_single_cpus = [cpus[0] for _, cpus in sorted_core_groups if cpus] # Take the first CPU from each core
        if len(available_single_cpus) < num_vcpus:
             socket_msg = f" on socket {target_socket}" if target_socket is not None and not allow_multi_socket else ""
             print(f"[ERROR] Not enough available physical cores{socket_msg} (using one thread per core strategy). Required: {num_vcpus}, Available cores: {len(available_single_cpus)}.")
             sys.exit(2)
        assigned_cpus = available_single_cpus[:num_vcpus]

    else:
        # Strategy 2: Use all logical CPUs from a core before moving to the next (--use-hyperthreads)
        if total_available_logical_cpus < num_vcpus:
             socket_msg = f" on socket {target_socket}" if target_socket is not None and not allow_multi_socket else ""
             print(f"[ERROR] Not enough available logical CPUs{socket_msg} (using hyper-threading strategy). Required: {num_vcpus}, Available logical CPUs: {total_available_logical_cpus}.")
             sys.exit(2)

        for _, logicals in sorted_core_groups:
            remaining_needed = num_vcpus - len(assigned_cpus)
            if remaining_needed <= 0:
                break # Already have enough CPUs

            # Add CPUs from this core's list until we have enough or the list runs out
            cpus_to_add = logicals[:remaining_needed]
            assigned_cpus.extend(cpus_to_add)

        # Final check (should not happen if total_available check passed, but good practice)
        if len(assigned_cpus) < num_vcpus:
            print(f"[ERROR] Internal error: Could not gather enough CPUs ({len(assigned_cpus)}/{num_vcpus}) even with hyper-threading strategy.")
            sys.exit(2)

    return sorted(assigned_cpus) # Return sorted list


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
    print(" Status: ✅ = Core fully available | ❌ = Core partially/fully used | * = CPU assigned")
    print("-------------------------------------------------------------")

    topology_map: Dict[int, Dict[int, List[int]]] = {}
    all_logical_cpus: Set[int] = set()

    for logical_cpu, core_id, socket_id in cpu_topology:
        topology_map.setdefault(socket_id, {}).setdefault(core_id, []).append(logical_cpu)
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
# Custom argparse *type* for "1,3,5" → [1, 3, 5]
# ---------------------------------------------------------------------------
def comma_separated_ints(value: str) -> List[int]:
    """
    Convert a comma-separated string of integers into a `list[int]`.

    Parameters
    ----------
    value : str
        The raw CLI value, e.g. "1,3,5".

    Returns
    -------
    list[int]
        A list of parsed, unique integers.

    Raises
    ------
    argparse.ArgumentTypeError
        If the input is empty, contains duplicates, or includes
        non-integer fragments.
    """
    try:
        numbers = [int(v.strip()) for v in value.split(",") if v.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"'{value}' is not a valid comma-separated sequence of integers."
        )
    if not numbers:
        raise argparse.ArgumentTypeError("The CPU list must not be empty.")
    if len(numbers) != len(set(numbers)):
        raise argparse.ArgumentTypeError("Duplicate CPU IDs detected.")
    return numbers


# ---------------------------------------------------------------------------
# Build the root `ArgumentParser` with six sub-commands
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    """
    Create and return the top-level `ArgumentParser` with all sub-commands.

    Returns
    -------
    argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="python3 pin_manager.py",
        description="Manage vCPU pinning for virtual machines.",
    )
    sub = parser.add_subparsers(
        dest="command", required=True, metavar="<command>"
    )

    # --- add --------------------------------------------------------------
    cmd_add = sub.add_parser("add", help="Automatically pin a new VM.")
    cmd_add.add_argument("vm_name", help="Name of the virtual machine.")
    cmd_add.add_argument("num_vcpus", type=int, help="Number of virtual CPUs.")
    cmd_add.add_argument(
        "socket_id",
        type=int,
        help="Preferred physical socket ID (e.g. 0 or 1).",
    )
    cmd_add.add_argument(
        "--multi-socket",
        action="store_true",
        help="Allow cores from any socket if required.",
    )
    cmd_add.add_argument(
        "--use-ht",
        action="store_true",
        help=(
            "Exhaust all hyper-threads of a core before moving to the next "
            "core (default is one thread per core)."
        ),
    )

    # --- add-manual -------------------------------------------------------
    cmd_manual = sub.add_parser(
        "add-manual", help="Manually pin a VM to specific logical CPUs."
    )
    cmd_manual.add_argument("vm_name", help="Name of the virtual machine.")
    cmd_manual.add_argument(
        "cpu_list",
        type=comma_separated_ints,
        metavar="<cpu1,cpu2,…>",
        help='Comma-separated logical CPU IDs, e.g. "1,3,5".',
    )

    # --- remove -----------------------------------------------------------
    cmd_remove = sub.add_parser("remove", help="Remove an existing pinning.")
    cmd_remove.add_argument("vm_name", help="Name of the virtual machine.")

    # --- informational commands ------------------------------------------
    sub.add_parser("list", help="List all VMs and their CPU assignments.")
    sub.add_parser("topology", help="Show host CPU topology.")
    sub.add_parser("free-cpus", help="Show currently unassigned logical CPUs.")

    return parser


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main() -> None:
    """Parse CLI arguments and dispatch to the selected sub-command."""
    # ---------------------------------------------------------------------
    # Safety check – root privileges are mandatory for pinning operations
    # ---------------------------------------------------------------------
    if os.geteuid() != 0:
        sys.exit("[ERROR] This script must be run as root.")

    parser = build_parser()
    args = parser.parse_args()

    # ---------------------------------------------------------------------
    # Load data that most commands need only once
    # ---------------------------------------------------------------------
    pinning_data = load_pinning()
    cpu_topology = get_cpu_topology()
    used_cpus: Set[int] = get_used_logical_cpus(pinning_data)
    system_cpus = {cpu for cpu, _, _ in cpu_topology}  # all logical CPUs

    # ---------------------------------------------------------------------
    # Command dispatcher – Python 3.10 structural pattern matching
    # ---------------------------------------------------------------------
    match args.command:
        # ----------------------------- add ------------------------------
        case "add":
            if args.vm_name in pinning_data:
                parser.error(f"VM '{args.vm_name}' is already pinned.")

            assigned_cpus = generate_cpu_allocation(
                cpu_topology=cpu_topology,
                num_vcpus=args.num_vcpus,
                used_cpus=used_cpus,
                target_socket=args.socket_id,
                allow_multi_socket=args.multi_socket,
                use_ht=args.use_ht,
            )
            pinning_data[args.vm_name] = assigned_cpus
            save_pinning(pinning_data)

            strategy = (
                "hyper-threads" if args.use_ht else "one thread per core"
            )
            print(
                f"\n✅ VM '{args.vm_name}' pinned automatically "
                f"({args.num_vcpus} vCPU, {strategy})"
            )
            print(f"   Logical CPUs: {assigned_cpus}")
            print("------------------------------------------------")
            print("oVirt pinning string:")
            print(build_ovirt_pinning_string(assigned_cpus))
            print("------------------------------------------------\n")

        # -------------------------- add-manual --------------------------
        case "add-manual":
            if args.vm_name in pinning_data:
                parser.error(f"VM '{args.vm_name}' is already pinned.")

            invalid_cpus = {c for c in args.cpu_list if c not in system_cpus}
            conflicting_cpus = {c for c in args.cpu_list if c in used_cpus}

            if invalid_cpus or conflicting_cpus:
                error_lines: list[str] = ["[ERROR] Validation failed:"]
                if invalid_cpus:
                    error_lines.append(f"  • Non-existent CPUs: {sorted(invalid_cpus)}")
                if conflicting_cpus:
                    error_lines.append(f"  • CPUs already in use: {sorted(conflicting_cpus)}")
                list_available_cpus(cpu_topology, used_cpus)
                sys.exit("\n".join(error_lines))

            pinning_data[args.vm_name] = sorted(args.cpu_list)
            save_pinning(pinning_data)

            print(f"\n✅ VM '{args.vm_name}' pinned manually")
            print(f"   Logical CPUs: {sorted(args.cpu_list)}")
            print("------------------------------------------------")
            print("oVirt pinning string:")
            print(build_ovirt_pinning_string(args.cpu_list))
            print("------------------------------------------------\n")

        # ---------------------------- remove ----------------------------
        case "remove":
            remove_vm(args.vm_name, pinning_data)

        # ----------------------------- list -----------------------------
        case "list":
            list_vms(pinning_data)

        # --------------------------- free-cpus --------------------------
        case "free-cpus":
            list_available_cpus(cpu_topology, used_cpus)

        # --------------------------- topology ---------------------------
        case "topology":
            print_cpu_topology(cpu_topology, used_cpus)

        # ---------------------------- default ---------------------------
        case _:
            # Should never happen due to argparse `required=True`
            parser.error("Unrecognized command.")  # pragma: no cover


if __name__ == "__main__":
    main()

