# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = source
BUILDDIR      = build
RAWDIR       = files

SOURCES       = $(shell find $(RAWDIR) -name "*.rst")
DOCUMENTS     = $(SOURCES:$(RAWDIR)/%.rst=$(SOURCEDIR)/%.rst)

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
html confluence: Makefile builtdocs
	@SPHINX_MODE="${@}" $(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

builtdocs: $(DOCUMENTS)

$(SOURCEDIR)/%.rst: $(RAWDIR)/%.rst
	@mkdir -p $(dir $@)
	vaguely-literate --single --output $@ $<

apidoc:
	sphinx-apidoc --force -o source/ ../src/dynamic_agent_runner/

clean:
	rm -rf build/*
	git clean -q -x -f source/*.rst

fresh: clean apidoc examples
	@echo "Local examples and API documentation rebuilt."
