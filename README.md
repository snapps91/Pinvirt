# 🧠 CPU Pinning Manager for oVirt VMs

A command-line utility written in pure Python (no external dependencies) to manage CPU pinning for virtual machines in oVirt environments.  
It generates pinning strings compatible with oVirt's **manual CPU pinning** mode and ensures CPU allocations are tracked and conflict-free.

---

## ✨ Features

- ✅ Allocate vCPUs to physical cores with optional socket targeting
- ✅ Avoid CPU reuse by tracking all pinning in a JSON file
- ✅ Support for multi-socket distribution
- ✅ View free logical CPUs
- ✅ Remove or reassign VMs safely
- ✅ Clear CLI output and formatting
- ✅ Fully type-annotated and cleanly structured

---

## 📦 Requirements

- Python 3.6+
- Linux system with `lscpu` available (usually pre-installed)

---

## 🚀 Usage

```bash
python3 pin_manager.py <command> [options]

