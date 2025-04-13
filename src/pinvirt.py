#!/usr/bin/env python3
import subprocess
import sys
import json
import os
from typing import List, Tuple, Dict, Set, Optional

PinningMap = Dict[str, List[int]]
CpuInfo = List[Tuple[int, int, int]]  # (logical_cpu, core_id, socket_id)

PINNING_FILE = "cpu_pinning_map.json"

def load_pinning() -> PinningMap:
    """
    Loads the CPU pinning data from the local JSON file.

    Returns:
        A dictionary mapping VM names to lists of pinned logical CPUs.
        If the file does not exist, returns an empty dictionary.

    Purpose:
        This function is used to persistently track which logical CPUs
        have been assigned to which VMs, so that we can avoid reassigning
        the same CPUs during pinning operations.
    """
    if not os.path.exists(PINNING_FILE):
        return {}
    with open(PINNING_FILE, "r") as file:
        return json.load(file)


def save_pinning(data: PinningMap) -> None:
    """
    Saves the current CPU pinning data to the local JSON file.

    Args:
        data: A dictionary mapping VM names to lists of logical CPUs.

    Purpose:
        Ensures that the pinning state (CPU allocations) is persistent
        between runs of the tool, enabling tracking and conflict prevention
        in a multi-VM setup.
    """
    with open(PINNING_FILE, "w") as file:
        json.dump(data, file, indent=2)


def get_cpu_topology() -> CpuInfo:
    """
    Retrieves the CPU topology of the host system using `lscpu`.

    Returns:
        A list of tuples representing logical CPU info in the format:
        (logical_cpu_id, core_id, socket_id)

    Purpose:
        Used to understand the physical and logical layout of CPUs on the host,
        including how logical CPUs map to physical cores and sockets (processors).
        This information is critical for hyper-threading awareness, NUMA
        optimization, and correct pinning of vCPUs to available physical cores.

    Raises:
        Exits the script if `lscpu` fails to execute (e.g., not found or permission issues).
    """
    try:
        output: str = subprocess.check_output(
            ["lscpu", "-p=CPU,CORE,SOCKET"], universal_newlines=True
        )
    except subprocess.SubprocessError as e:
        print(f"[ERROR] Failed to run lscpu: {e}")
        sys.exit(1) 
    
    topology: CpuInfo = []
    for line in output.splitlines():
        if line.startswith("#"):
            continue  # Skip comment lines
        parts = line.strip().split(",")
        if len(parts) == 3: 
            logical_cpu, core_id, socket_id = map(int, parts)
            topology.append((logical_cpu, core_id, socket_id))
    return topology

def get_used_logical_cpus(pinning_data: PinningMap) -> Set[int]:
    """
    Extracts the set of all logical CPUs currently assigned to VMs.

    Args:
        pinning_data: Dictionary mapping VM names to lists of logical CPU IDs.

    Returns:
        A set of logical CPU IDs that are already in use.

    Purpose:
        Used to avoid CPU assignment conflicts by filtering out CPUs
        already pinned to active VMs.
    """
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
) -> List[int]:
    """
    Allocates a list of available logical CPUs to be used for vCPU pinning.

    Args:
        cpu_topology: List of tuples (logical_cpu, core_id, socket_id).
        num_vcpus: Number of vCPUs requested for the VM.
        used_cpus: Set of logical CPUs already in use.
        target_socket: Optional socket ID to prefer (defaults to None).
        allow_multi_socket: If True, allows using CPUs from any socket.

    Returns:
        A list of logical CPU IDs, one per physical core, to assign to vCPUs.

    Behavior:
        - Picks only the first logical thread per physical core (HT-aware).
        - Respects socket constraint unless allow_multi_socket is enabled.
        - Exits with error if not enough physical cores are available.

    Purpose:
        Provides conflict-free, hyperthreading-aware logical CPU assignments
        that comply with requested vCPU count and optional socket affinity.
    """
    core_map: Dict[Tuple[int, int], int] = {}

    for logical_cpu, core_id, socket_id in cpu_topology:
        if target_socket is not None and not allow_multi_socket and socket_id != target_socket:
            continue
        if logical_cpu in used_cpus:
            continue
        core_key: Tuple[int, int] = (socket_id, core_id)
        if core_key not in core_map:
            core_map[core_key] = logical_cpu  # one thread per physical core

    sorted_cores: List[Tuple[int, int]] = sorted(core_map.keys())
    if len(sorted_cores) < num_vcpus:
        print(f"[ERROR] Not enough available physical cores. Required: {num_vcpus}, Available: {len(sorted_cores)}.")
        sys.exit(2)

    return [core_map[key] for key in sorted_cores[:num_vcpus]]


def build_ovirt_pinning_string(assigned_cpus: List[int]) -> str:
    """
    Formats a list of logical CPUs into a pinning string compatible with oVirt.

    Args:
        assigned_cpus: A list of logical CPU IDs to be assigned to vCPUs.

    Returns:
        A string in the format "0#<cpu0>_1#<cpu1>_2#<cpu2>..." representing
        the vCPU-to-pCPU mapping.

    Purpose:
        This output can be pasted directly into oVirt’s "Manual CPU Pinning"
        field when configuring a virtual machine.
    """
    return "_".join(f"{v_cpu}#{p_cpu}" for v_cpu, p_cpu in enumerate(assigned_cpus))


def list_vms(pinning_data: PinningMap) -> None:
    print("\n📋 Currently pinned VMs:")
    if not pinning_data:
        print("  (none)")
        return

    for vm_name, cpus in pinning_data.items():
        ovirt_string: str = build_ovirt_pinning_string(cpus)
        print(f"  🖥️ {vm_name}")
        print(f"    • CPUs assigned   : {cpus}")
        print(f"    • oVirt pinning   : {ovirt_string}")
    print()


def list_available_cpus(cpu_topology: CpuInfo, used_cpus: Set[int]) -> None:
    all_logical: List[int] = sorted(set(cpu for cpu, _, _ in cpu_topology))
    available: List[int] = [cpu for cpu in all_logical if cpu not in used_cpus]
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
    print("\n🧠 CPU Topology (Logical CPUs per Physical Core)")
    print("------------------------------------------------")

    # Organize by socket -> core -> logical CPUs
    topology: Dict[int, Dict[int, List[int]]] = {}

    for logical_cpu, core_id, socket_id in cpu_topology:
        topology.setdefault(socket_id, {}).setdefault(core_id, []).append(logical_cpu)

    for socket_id in sorted(topology):
        print(f"Socket {socket_id}:")
        for core_id in sorted(topology[socket_id]):
            logicals = sorted(topology[socket_id][core_id])
            status = "✅" if all(cpu not in used_cpus for cpu in logicals) else "❌"
            cpu_str = "][".join(f"{cpu:3d}" for cpu in logicals)
            print(f"  Core {core_id}: [{cpu_str}]   {status}")
        print()


def print_help() -> None:
    print("""
Usage:
  python3 pin_manager.py --add <vm_name> <num_vcpus> <socket_id> [--multi-socket] Add a new VM with pinned CPUs
  python3 pin_manager.py --remove <vm_name>                                       Remove a VM and free its CPUs
  python3 pin_manager.py --list                                                   List all pinned VMs
  python3 pin_manager.py --free-cpus                                              Show available logical CPUs
  python3 pin_manager.py --topology                                               Show topology logical CPUs
  python3 pin_manager.py --help                                                   Show this help message
""")


def main() -> None:
    args: List[str] = sys.argv
    if len(args) < 2 or args[1] == "--help":
        print_help()
        return

    action: str = args[1]
    pinning_data: PinningMap = load_pinning()
    cpu_topology: CpuInfo = get_cpu_topology()
    used_cpus: Set[int] = get_used_logical_cpus(pinning_data)

    if action == "--add" and len(args) >= 5:
        vm_name: str = args[2]
        try:
            num_vcpus: int = int(args[3])
            socket_id: int = int(args[4])
        except ValueError:
            print("[ERROR] num_vcpus and socket_id must be integers.")
            sys.exit(1)

        allow_multi_socket: bool = "--multi-socket" in args

        if vm_name in pinning_data:
            print(f"[WARN] VM '{vm_name}' is already pinned: {pinning_data[vm_name]}")
            sys.exit(1)

        assigned_cpus: List[int] = generate_cpu_allocation(
            cpu_topology, num_vcpus, used_cpus, socket_id, allow_multi_socket
        )
        pinning_data[vm_name] = assigned_cpus
        save_pinning(pinning_data)

        print(f"\n✅ Successfully pinned VM '{vm_name}' with {num_vcpus} vCPU(s)")
        print("------------------------------------------------")
        print(build_ovirt_pinning_string(assigned_cpus))
        print("------------------------------------------------\n")

    elif action == "--remove" and len(args) == 3:
        remove_vm(args[2], pinning_data)

    elif action == "--list":
        list_vms(pinning_data)

    elif action == "--free-cpus":
        list_available_cpus(cpu_topology, used_cpus)
    elif action == "--topology":
        print_cpu_topology(cpu_topology, used_cpus)
    else:
        print("[ERROR] Invalid command or missing arguments.")
        print_help()


if __name__ == "__main__":
    main()
