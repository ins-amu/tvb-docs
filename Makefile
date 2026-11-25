# Thin wrapper around make.py.
#
# The task definitions live in make.py so contributors without `make`
# (notably on Windows) can run the same tasks:
#
#     python make.py check
#
# `make check` and `python make.py check` are equivalent.

PYTHON ?= python3
TASKS := help setup refs docs test check lite-setup lite all serve clean

.DEFAULT_GOAL := help
.PHONY: $(TASKS)

$(TASKS):
	@$(PYTHON) make.py $@
