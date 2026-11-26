# Thin wrapper around make.py.
#
# The task definitions live in make.py so contributors without `make`
# (notably on Windows) can run the same tasks:
#
#     python make.py        # runs default `dev` task
#     python make.py check
#
# `make check` and `python make.py check` are equivalent.

PYTHON ?= python3
TASKS := dev apidoc docs lite all serve check refs test setup lite-setup status clean clean-all help

.DEFAULT_GOAL := dev
.PHONY: $(TASKS)

$(TASKS):
	@$(PYTHON) make.py $@
