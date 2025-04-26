# CPU Pinning Manager

**CPU Pinning Manager** is a Python tool that helps automate and manage CPU core assignments (pinning) for Virtual Machines (VMs) on a Linux host.  
It retrieves the CPU topology using `lscpu`, manages pinning assignments via a local JSON database, and generates oVirt-compatible pinning strings.

## Features

- Automatic vCPU to pCPU (physical CPU) allocation based on CPU topology
- Support for multi-socket CPU environments
- Optional hyper-threading-aware allocations
- Manual pinning to specific logical CPUs
- Listing of pinned VMs and available CPUs
- Display of host CPU topology and core utilization
- Easy removal of VM pinning records
- Persistent storage of assignments in a local `cpu_pinning_map.json` file

## Requirements

- Python 3.x
- `lscpu` command available on the system (from `util-linux` package)

## Usage

```bash
python3 pin_manager.py <command> [options]
```

### Commands

- `--add <vm_name> <num_vcpus> <socket_id> [--multi-socket] [--use-hyperthreads]`  
  Automatically assign logical CPUs to a new VM.
  
- `--add-manual <vm_name> <cpu_list>`  
  Manually assign specific logical CPUs to a VM. Example: `"0,2,4,6"`

- `--remove <vm_name>`  
  Remove a VM's pinning record and free its CPUs.

- `--list`  
  List all currently pinned VMs and their CPU assignments.

- `--topology`  
  Show the host's CPU topology and core utilization.

- `--free-cpus`  
  Show the logical CPUs that are currently available.

- `--help`  
  Show the help message.

## Examples

### Add a VM automatically with hyper-threading

```bash
python3 pin_manager.py --add my-vm 4 0 --use-hyperthreads
```

Assigns 4 vCPUs to `my-vm`, preferring socket 0 and using hyper-threading.

### Manually pin a VM to specific CPUs

```bash
python3 pin_manager.py --add-manual my-vm "1,3,5,7"
```

Assigns logical CPUs 1, 3, 5, and 7 to `my-vm`.

### List all pinned VMs

```bash
python3 pin_manager.py --list
```

### Show host CPU topology

```bash
python3 pin_manager.py --topology
```

### Remove a pinned VM

```bash
python3 pin_manager.py --remove my-vm
```

## Pinning Output Format

When a VM is pinned, the tool generates an oVirt-compatible string:

```
vCPU0#pCPU0_vCPU1#pCPU1_vCPU2#pCPU2_...
```

Example output:

```
0#1_1#3_2#5_3#7
```

This string can be directly copied into the "CPU Pinning" field in oVirt.

## Notes

- If the CPU topology cannot be retrieved or if there are not enough CPUs available, the tool will exit with an error.
- By default, one logical CPU per core is assigned unless `--use-hyperthreads` is specified.
- Duplicate CPU assignments are prevented automatically.
- Assignments are stored persistently in the local `cpu_pinning_map.json` file.

## License

This project is licensed under the MIT License.  
Feel free to use, modify, and distribute it with attribution.