NAME = connector
BUILDENV = ../glue

all:
	@echo "Template Makefile, to be filled with build and install targets"

$(BUILDENV)/bin/python:
	make -C $(BUILDENV) bin/python

clean:
	find $(CURDIR) \( -name "*.pyc" -o -name "*~" \) -delete
buildclean: clean
	rm -rf eggs develop-eggs parts .installed.cfg bin src/vigilo_connector.egg-info

apidoc: doc/apidoc/index.html $(BUILDENV)/bin/python
doc/apidoc/index.html: src/vigilo
	rm -rf $(CURDIR)/doc/apidoc/*
	PYTHONPATH=$(BUILDENV) $(BUILDENV)/bin/python "$$(which epydoc)" -o $(dir $@) -v \
		   --name Vigilo --url http://www.projet-vigilo.org \
		   --docformat=epytext $^

lint: $(BUILDENV)/bin/python
	$(BUILDENV)/bin/python "$$(which pylint)" --rcfile=$(BUILDENV)/extra/pylintrc src/vigilo

tests: $(BUILDENV)/bin/python
	PYTHONPATH=$(BUILDENV):src VIGILO_SETTINGS_MODULE=settings_tests \
		$(BUILDENV)/bin/nosetests \
		--with-coverage --cover-package=vigilo.connector \
		tests

.PHONY: all clean buildclean apidoc lint tests

