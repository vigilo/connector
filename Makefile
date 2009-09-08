NAME := connector
BUILDENV := ../glue

all:
	@echo "Template Makefile, to be filled with build and install targets"

$(BUILDENV)/bin/python:
	make -C $(BUILDENV) bin/python

clean:
	find $(CURDIR) \( -name "*.pyc" -o -name "*~" \) -delete
buildclean: clean
	rm -rf eggs develop-eggs parts .installed.cfg bin src/vigilo_connector.egg-info

EPYDOC := $(shell [ -f $(BUILDENV)/bin/epydoc ] && echo $(BUILDENV)/bin/epydoc || echo $(PYTHON) /usr/bin/epydoc)
apidoc: doc/apidoc/index.html
doc/apidoc/index.html: src/vigilo/$(NAME)
	rm -rf $(CURDIR)/doc/apidoc/*
	PYTHONPATH=$(BUILDENV):src $(EPYDOC) -o $(dir $@) -v \
		   --name Vigilo --url http://www.projet-vigilo.org \
		   --docformat=epytext vigilo.$(NAME)

PYLINT := $(shell [ -f $(BUILDENV)/bin/pylint ] && echo $(BUILDENV)/bin/pylint || echo $(PYTHON) /usr/bin/pylint)
lint: $(PYTHON) src/vigilo/$(NAME)
	-PYTHONPATH=src $(PYLINT) \
		--rcfile=$(BUILDENV)/extra/pylintrc src/vigilo/$(NAME)

tests: $(BUILDENV)/bin/python
	PYTHONPATH=$(BUILDENV):src VIGILO_SETTINGS_MODULE=settings_tests \
		$(BUILDENV)/bin/nosetests \
		--with-coverage --cover-package=vigilo.connector \
		tests

.PHONY: all clean buildclean apidoc lint tests

