# Pinvirt - oVirt/OLVM/RHV Cpu Pinning Tool

[![RPM Available](https://img.shields.io/badge/RPM-Available-brightgreen)](https://github.com/snapps91/Pinvirt/releases)

**Pinvirt** is a lightweight CPU Pinning Manager for Virtual Machines (VMs) on Linux systems.

It automatically assigns logical CPUs to VMs based on the host CPU topology, supporting multi-socket and hyper-threaded configurations.
Pinvirt also generates oVirt-compatible CPU pinning strings for seamless integration with virtualization platforms.

---

## ✨ Features

- Automatic CPU pinning based on system topology (`lscpu`)
- Support for hyper-threading and multi-socket systems
- Manual CPU assignment option
- Persistent storage of CPU assignments (`cpu_pinning_map.json`)
- Clear CLI interface for managing pinned CPUs
- RPM packages for easy installation

---

## 📦 Installation

You can install **Pinvirt** by downloading the appropriate RPM package for your system:

### Oracle Linux 8

```bash
sudo dnf install https://github.com/snapps91/Pinvirt/releases/download/v1.1.1/pinvirt-1.1.1-3.el8.noarch.rpm
```

### Oracle Linux 9

```bash
sudo dnf install https://github.com/snapps91/Pinvirt/releases/download/v1.1.1/pinvirt-1.1.1-3.el9.noarch.rpm
```

✅ After installation, you can access the CLI tool:

```bash
pinvirt --help
```

---

## 👋 Usage

Pinvirt provides several commands to manage VM CPU pinning:

```bash
pinvirt add <vm_name> <num_vcpus> <socket_id> [--multi-socket] [--use-ht]
pinvirt add-manual <vm_name> <cpu_list>
pinvirt remove <vm_name>
pinvirt list
pinvirt topology
pinvirt free-cpus
pinvirt --help
```

Example: Automatically pin 4 vCPUs for a VM called "vm01" on socket 0:

```bash
pinvirt add vm01 4 0
```

Example: Manually assign logical CPUs 1, 3, 5 to a VM called "vm02":

```bash
pinvirt add-manual vm02 1,3,5
```

---

## 🛠 Requirements

- Python 3.x
- `lscpu` (provided by the `util-linux` package)

---

## 📈 Roadmap

- [x] Initial stable release
- [x] RPM packaging for Oracle Linux 8 and 9
- [ ] Advanced multi-socket and NUMA-aware CPU allocation
- [ ] Direct integration with oVirt/RHV APIs
- [ ] Support for additional Linux distributions

---

## 🛡 License

This project is licensed under the MIT License.

---

## Developer Guide
TODO