Name:           pinvirt
Version:        1.1.1
Release:        3%{?dist}
Summary:        CPU Pinning Manager for Virtual Machines (Pinvirt)

License:        MIT
URL:            https://github.com/snapps91/Pinvirt
Source0:        %{name}.py

BuildArch:      noarch
Requires:       python3, util-linux

%description
Pinvirt is a lightweight CPU pinning manager for Linux Virtual Machines (VMs).
It automatically manages vCPU to pCPU mappings and generates oVirt-compatible pinning strings.

%prep
# Nothing to prepare

%build
# Nothing to build

%install
mkdir -p %{buildroot}/usr/local/bin
install -m 0755 %{SOURCE0} %{buildroot}/usr/local/bin/pinvirt

mkdir -p %{buildroot}/etc/pinvirt

%files
/usr/local/bin/pinvirt
%dir /etc/pinvirt

%changelog
* Sun Apr 27 2025 Giacomo Failla <giacomo.failla@cheope.io> - 1.0.1-1
- Defined /etc/pinvirt as the configuration directory (was missing before).
* Sat Apr 26 2025 Giacomo Failla <giacomo.failla@cheope.io> - 1.0-1
- Initial release of Pinvirt CPU Pinning Manager.
