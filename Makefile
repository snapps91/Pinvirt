SPEC=rpm/pinvirt.spec

build-rpm:
	cp src/pinvirt.py ~/rpmbuild/SOURCES/
	cp $(SPEC) ~/rpmbuild/SPECS/
	rpmbuild -ba ~/rpmbuild/SPECS/$(notdir $(SPEC))

install-rpm:
	sudo rpm -ivh ~/rpmbuild/RPMS/noarch/pinvirt-*.rpm

clean-rpm:
	rm -f ~/rpmbuild/SOURCES/pinvirt.py
	rm -f ~/rpmbuild/SPECS/pinvirt.spec

run:
	python3 ./src/pinvirt.py --help

.PHONY: build-rpm install-rpm clean-rpm run
