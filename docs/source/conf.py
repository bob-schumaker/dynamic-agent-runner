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
import subprocess
import sys
from urllib.parse import urlparse

import tomllib

DOCS_SOURCE_DIR = os.path.abspath(os.path.dirname(__file__))
DOCS_DIR = os.path.dirname(DOCS_SOURCE_DIR)
REPO_ROOT = os.path.dirname(DOCS_DIR)
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))


def _load_project_metadata() -> dict:
    """Read Sphinx project metadata from ``pyproject.toml`` when available."""
    pyproject_path = os.path.join(REPO_ROOT, "pyproject.toml")
    try:
        with open(pyproject_path, "rb") as handle:
            pyproject_data = tomllib.load(handle)
    except OSError:
        return {}

    return pyproject_data.get("project", {})


def _git_config_value(key: str) -> str:
    """Return a git config value for this repository, if available."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", key],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return ""

    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _git_config_values(pattern: str) -> list[str]:
    """Return git config values matching a key pattern."""
    try:
        result = subprocess.run(
            ["git", "config", "--get-regexp", pattern],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []

    if result.returncode != 0:
        return []

    values = []
    for line in result.stdout.splitlines():
        _key, _, value = line.partition(" ")
        if value:
            values.append(value.strip())
    return values


def _format_author(name: str = "", email: str = "") -> str:
    """Format author metadata for Sphinx."""
    if name and email:
        return f"{name} <{email}>"
    return name or email


def _project_name_from_remote_url(remote_url: str) -> str:
    """Return the trailing repository name from a remote URL."""
    if not remote_url:
        return ""

    if ":" in remote_url and "://" not in remote_url:
        remote_path = remote_url.rsplit(":", 1)[-1]
    else:
        remote_path = urlparse(remote_url).path

    project_name = remote_path.rstrip("/").rsplit("/", 1)[-1]
    if project_name.endswith(".git"):
        project_name = project_name[:-4]
    return project_name


def _remote_project_name() -> str:
    """Return a trailing repository name from configured git remotes."""
    remote_urls = [
        _git_config_value("remote.origin.url"),
        *_git_config_values(r"^remote\..*\.url$"),
    ]
    for remote_url in remote_urls:
        project_name = _project_name_from_remote_url(remote_url)
        if project_name:
            return project_name
    return ""


def _load_author(project_metadata: dict) -> str:
    """Read author metadata, falling back to git config when needed."""
    authors = project_metadata.get("authors") or []
    if authors:
        author = authors[0]
        if isinstance(author, dict):
            return _format_author(author.get("name", ""), author.get("email", ""))
        return str(author)

    return _format_author(
        _git_config_value("user.name"),
        _git_config_value("user.email"),
    )


_project_metadata = _load_project_metadata()
_author = _load_author(_project_metadata)


# -- Project information -----------------------------------------------------

project = (
    _project_metadata.get("name")
    or _remote_project_name()
    or os.path.basename(REPO_ROOT)
)
author = _author
copyright = "Copyright (c) 2015–2026, The Software Cobbler."

# The full version, including alpha/beta/rc tags
release = _project_metadata.get("version", "local")
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

rst_epilog = f"""
.. |copyright| replace:: {copyright}
"""

if os.environ.get("SPHINX_MODE") == "confluence":
    from selenium import webdriver

    from werner.connect import SeleniumSSOAuthAdapter
    from werner.sparta.oracle_sso import OracleSingleSignOn

    confluence_auth_cookie = "seraph.confluence"

    def _configure_confluence_session(session):
        """Install Selenium SSO auth on confluencebuilder's requests session."""
        session.auth = SeleniumSSOAuthAdapter(
            OracleSingleSignOn,
            driver_factory=lambda: webdriver.Firefox(),
            expected_cookie=confluence_auth_cookie,
            base_url=confluence_server_url,
            target_url=confluence_server_url,
            manual_login=True,
            manual_login_message=(
                "Complete the Oracle Confluence login in the opened Firefox "
                "window so Sphinx can publish the documentation."
            ),
        )

    confluence_server_url = "https://confluence.oraclecorp.com/confluence/"
    confluence_publish = True
    confluence_space_key = "INDCON"
    confluence_parent_page = "Documentation"
    confluence_page_hierarchy = True
    confluence_cleanup_from_root = True
    confluence_request_session_override = _configure_confluence_session

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "alabaster"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]
