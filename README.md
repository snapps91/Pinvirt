# Pinvirt - oVirt/OLVM/RHV Cpu Pinning Tool

[![RPM Available](https://img.shields.io/badge/RPM-Available-brightgreen)](https://github.com/snapps91/Pinvirt/releases) [![Test and Build RPM](https://github.com/snapps91/Pinvirt/actions/workflows/test-build.yml/badge.svg)](https://github.com/snapps91/Pinvirt/actions/workflows/test-build.yml)

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

### Oracle Linux 8.x

```bash
sudo dnf install https://github.com/snapps91/Pinvirt/releases/download/v1.1.1/pinvirt-1.1.1-3.el8.noarch.rpm
```

### Oracle Linux 9.x

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

- Python >= 3.6
- `lscpu` (provided by the `util-linux` package)

---

## 💡 Real-World use cases

**Oracle Licensing Compliance (Hard Partitioning)**

Oracle only allows you to count the CPU cores that are *statically allocated* to a VM.
With oVirt + Pinvirt, you can prove that a VM is strictly confined to a specific set of cores (hard partitioning), avoiding unnecessary licensing costs.
This is especially useful in environments where Oracle Database is installed on KVM/OLVM, and it’s necessary to prove that the VM does not exceed a certain CPU allocation.

**Performance Tuning for Critical Workloads**

Dedicated pinning for databases or real-time applications (e.g., PostgreSQL, Redis, MySQL) helps reduce jitter from CPU scheduling.
This prevents workloads from being migrated to less performant or shared cores.

**NUMA Topology-Aware Environments**

In NUMA systems, assigning CPU and RAM within the correct NUMA node helps avoid latency caused by remote memory access.

 **Infrastructure as Code / DevOps Automation**

Can be integrated into provisioning toolchains (e.g., Ansible, Terraform) to automate the setup of high-performance VMs.

**Compliance / Audit / Technical Documentation**

The structured and persistent generation of CPU assignments is useful for internal audits, or to export configurations as part of technical documentation.

---

## 📈 Roadmap

- [x] Initial stable release
- [x] RPM packaging for Oracle Linux 8 and 9
- [ ] Direct integration with oVirt/OLVM/RHV APIs with oVirt SDK 4

---

## 🛡 License

This project is licensed under the MIT License.

---

## Developer Guide
TODO