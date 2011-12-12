NAME := connector
all: settings.ini build

include buildenv/Makefile.common

settings.ini: settings.ini.in
	sed -e 's,@LOCALSTATEDIR@,$(LOCALSTATEDIR),g' $^ > $@

install: $(PYTHON) settings.ini build
	$(PYTHON) setup.py install --record=INSTALLED_FILES
install_pkg: $(PYTHON) settings.ini build
	$(PYTHON) setup.py install --single-version-externally-managed --root=$(DESTDIR)

lint: lint_pylint
tests: tests_nose
doc: apidoc
clean: clean_python
	rm -f settings.ini
