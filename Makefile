NAME := connector
all: build

include buildenv/Makefile.common

install: $(PYTHON)
	$(PYTHON) setup.py install --root=$(DESTDIR) --record=INSTALLED_FILES
install_pkg: $(PYTHON)
	$(PYTHON) setup.py install --single-version-externally-managed --root=$(DESTDIR)

lint: lint_pylint
tests: tests_nose
clean: clean_python
