NAME := connector
all: build
include ../glue/Makefile.common
lint: lint_pylint
tests: tests_nose
