NAME := connector
all: build

include buildenv/Makefile.common

install:
	$(PYTHON) setup.py install --single-version-externally-managed --root=$(DESTDIR) --record=INSTALLED_FILES

lint: lint_pylint
tests: tests_nose
clean: clean_python
