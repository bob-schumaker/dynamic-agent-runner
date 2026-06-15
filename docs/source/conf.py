# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# References:
#   https://www.gisellezeno.com/tutorials/sphinx-for-python-documentation.html
#   https://samnicholls.net/2016/06/15/how-to-sphinx-readthedocs/
#   https://thomas-cokelaer.info/tutorials/sphinx/docstring_python.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import re
import sys

DOCS_SOURCE_DIR = os.path.abspath(os.path.dirname(__file__))
DOCS_DIR = os.path.dirname(DOCS_SOURCE_DIR)
REPO_ROOT = os.path.dirname(DOCS_DIR)
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))


def _load_release(default: str = "local") -> str:
    """Read the package version from ``pyproject.toml`` when available."""
    pyproject_path = os.path.join(REPO_ROOT, "pyproject.toml")
    try:
        with open(pyproject_path, "rt", encoding="utf-8") as handle:
            pyproject_text = handle.read()
    except OSError:
        return default

    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject_text, re.MULTILINE)
    if not match:
        return default
    return match.group(1)


# -- Project information -----------------------------------------------------

project = os.path.basename(REPO_ROOT)
copyright = "2026, Oracle Corporation"
author = "Bob Schumaker"

# The full version, including alpha/beta/rc tags
release = _load_release()
version = release


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinxcontrib.confluencebuilder",
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []

if os.environ.get("SPHINX_MODE") == "confluence":
    from selenium import webdriver

    from werner.connect import SeleniumSSOAuthAdapter
    from werner.sparta import OCIPasswordManager, OracleConfluenceClient
    from werner.sparta.oracle_sso import OracleSingleSignOn, PICAUTH

    class SphinxOracleConfluenceClient(OracleConfluenceClient):
        """Use the Selenium-backed SSO flow for Sphinx Confluence publishing."""

        def handle_authentication(self, security_descriptor):
            del security_descriptor

            signon_handler = OracleSingleSignOn(
                self,
                notifier=self.notify,
                logger=self.logger,
            )
            self._auth = SeleniumSSOAuthAdapter(
                signon_handler,
                driver_factory=webdriver.Firefox,
                expected_cookie=PICAUTH,
                logger=self.logger,
                manual_login=True,
                manual_login_message=(
                    "Complete the Oracle Confluence login in the opened Firefox "
                    "window so Sphinx can publish the documentation."
                ),
            )
            self.session.auth = self._auth
            if not self.validate_auth():
                raise RuntimeError(
                    "Unable to authenticate Oracle Confluence for Sphinx publishing."
                )

    oci_manager = OCIPasswordManager()
    descriptors = [OracleConfluenceClient.security_descriptor()]
    auth = oci_manager.get_descriptors(descriptors, interactive=False)

    conf_client = SphinxOracleConfluenceClient(auth)

    confluence_server_cookies = conf_client.session.cookies.get_dict()
    confluence_publish = True
    confluence_space_key = "INDCON"
    confluence_parent_page = "Documentation"
    confluence_server_url = "https://confluence.oraclecorp.com/"
    confluence_page_hierarchy = True
    confluence_cleanup_from_root = True

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "alabaster"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]
