#!/usr/bin/env python
"""
OCI Build doesn't have a "poetry" or "PDM" builder option, so let's use
the python step to run am appropriate build.
"""
import logging
import os
import re
import sys
from subprocess import STDOUT, CalledProcessError, check_output
from typing import List, Optional, Tuple

KNOWN_BUILDERS = ["poetry", "pdm"]

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"
COLORS = {
    "WARNING": YELLOW,
    "INFO": BLUE,
    "DEBUG": WHITE,
    "CRITICAL": YELLOW,
    "ERROR": RED,
}


class PatchFile:
    """Patch a file on disk."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._contents = None

    @property
    def contents(self) -> List[str]:
        """Return the contents of the file we want to patch, just once."""
        if not self._contents:
            with open(self._path, "rt", encoding="UTF-8") as handle:
                self._contents = handle.readlines()
        return self._contents

    def find(self, pattern: str) -> Tuple[Optional[int], Optional[str]]:
        """Find the line with pattern in it."""
        for idx, line in enumerate(self.contents):
            if pattern in line:
                return (idx, line)
        return None, None

    def patch(self, pattern: str, match: str, replace: str) -> bool:
        """Find a string and patch that line."""
        line_idx, line = self.find(pattern)
        if line_idx and line:
            self.contents[line_idx] = line.replace(match, replace)
            return True
        return False

    def insert(self, pattern: str, insertion: str, before: bool = True) -> None:
        """Add a line to the file."""
        line_idx, line = self.find(pattern)
        if line_idx and line and self._contents:
            split = line_idx if before else line_idx + 1
            chop1 = slice(0, split)
            chop2 = slice(split, len(self.contents))
            self._contents = (
                self._contents[chop1] + [insertion + "\n"] + self.contents[chop2]
            )

    def replace(self, contents: str) -> None:
        """Replace the entire contents of the file."""
        self._contents = contents

    def save(self) -> None:
        """Save the changes"""
        if self._contents:
            with open(self._path, "wt", encoding="UTF-8") as handle:
                handle.writelines(self._contents)
            self._contents = None

    def dump(self) -> None:
        """Dump the file."""
        if self._contents:
            for line in self._contents:
                print(line)


class CustomFormatter(logging.Formatter):
    """Logging Formatter to add colors and count warning / errors"""

    def format(self, record):
        levelname = record.levelname
        if levelname in COLORS:
            levelname_color = (
                COLOR_SEQ % (30 + COLORS[levelname]) + levelname + RESET_SEQ
            )
            record.levelname = levelname_color
        log_format = f"%(asctime)s %(levelname)-{len(COLOR_SEQ) + len(RESET_SEQ) + 5}s {COLOR_SEQ % (30 + CYAN)}Custom    {RESET_SEQ} - %(message)s"
        formatter = logging.Formatter(log_format)
        return formatter.format(record)


class BuildScript:
    """Collect steps to run for a build in a consistent fashion."""

    def __init__(self):
        self.build_script = []
        self.verbose = True

    @staticmethod
    def run_command(cmd, stdin=None, cwd=None, quiet=False, split=False):
        """
        Run a command and return its output, if any.

        The command is an array of entries that make up the command, e.g.
        ['ssh', '-F', 'config', 'root@remotehost']
        """
        if quiet:
            stderr = None
        else:
            stderr = STDOUT
        try:
            output = check_output(cmd, stdin=stdin, stderr=stderr, cwd=cwd)
            errorcode = 0
        except CalledProcessError as error:
            output = error.output
            errorcode = error.returncode

        output = output.decode("UTF-8")
        if split:
            output = output.splitlines()
        return (errorcode, output)

    def verbose_command(self, cmd, **kw_args) -> Tuple[int, str]:
        """Run the command and show the output."""
        logging.info("Running command %s", cmd)
        error, output = self.run_command(cmd, **kw_args)
        logging.info("Error: %d\n%s", error, output)

    def add(self, command, check_failure=True, show_output=False):
        """Add a command to the script."""
        if not isinstance(command, list):
            command = [command]
        self.build_script.append((check_failure, show_output, command))

    def install_tool(self, builder_tool: str, base_path: Optional[str] = None) -> None:
        """Install the specified tool, with a specific version, if specified."""
        package_name = builder_tool
        if base_path is None:
            base_path = self.find_python()
        # Is there an explicit package version of the tool to use? (e.g. a file)
        version_package = os.environ.get(f"{builder_tool}_PACKAGE".upper())
        if version_package:
            package_name = version_package
        else:
            for varname in (f"{builder_tool}_VERSION".upper(), "BUILD_SYSTEM_VERSION"):
                build_system_version = os.environ.get(varname)
                if build_system_version:
                    package_name = f"{builder_tool}>={build_system_version}"
                    break
        self.add([base_path + "python3", "-m", "pip", "install", package_name])

    @staticmethod
    def branching_model():
        """This is an attempt to map 'A Successful git Branching Model' onto PEP-440
        https://www.python.org/dev/peps/pep-0440/
        https://nvie.com/posts/a-successful-git-branching-model/
        """
        release_version = os.environ.get("FORCED_VERSION")
        if release_version:
            return True, f"{release_version}"

        release_version = os.environ.get("RELEASE_VERSION")
        develop_version = os.environ.get("DEVELOP_VERSION")
        # Caclulate the development version. Assume we want to roll the
        # lowest number. Should do semantic versioning, but...
        if not develop_version:
            release_bits = release_version.split(".")
            release_bits[-1] = str(int(release_bits[-1]) + 1)
            develop_version = ".".join(release_bits)

        build_offset = int(os.environ.get("BUILD_OFFSET", "0"))
        build_number = os.environ.get("BLD_NUMBER", build_offset)
        branch = os.environ.get("BLD_BRANCH", "")

        if build_number in ("OCIBUILD-SNAPSHOT", "user-dev"):
            build_number = "0"
        elif build_offset:
            build_number = str(max(int(build_number) - build_offset, 0))

        # Forced release version (if ocibuild has "release-*" in triggerOnCommitBranches)
        match = re.match(r"release-(.*)", branch)
        if match:
            release_version = match.group(1)
            branch = "master"
        else:
            # If this is a back-compat branch, build it like it was master
            match = re.match(r"support-(.*)", branch)
            if match:
                branch = "master"

        if branch in ("master", "main"):
            return True, f"{release_version}.{build_number}"

        # Deal with develop branches
        if "beta" in branch or "develop" in branch:
            tag = "beta"
        else:
            tag = "alpha"
        return False, f"{develop_version}-{tag}{build_number}"

    @staticmethod
    def find_python() -> str:
        """Find the path to a python, if at all possible."""
        logging.info("Looking for Python 3 installation.")
        runner = BuildScript()
        error, output = runner.run_command([sys.executable, "--version"])
        if not error and "Python 3" in output:
            return os.path.dirname(sys.executable) + "/"
        try:
            runner.run_command(["python3", "--version"])
        except FileNotFoundError:
            for pypath in ["/root/py39/bin/", "/root/py38/bin/", "/root/py37/bin/"]:
                if os.path.exists(pypath):
                    return pypath
        return ""

    def execute(self):
        """Run the build script."""
        for check_failure, show_output, command in self.build_script:
            if self.verbose:
                logging.info("Executing: %s", " ".join(command))
            error, output = self.run_command(command)
            if check_failure and error:
                logging.error(output)
                sys.exit(error)
            elif show_output:
                logging.info(output)


def main():
    """Build the current project using the selected build tool under OCI build."""
    root = logging.getLogger()
    loglevel = logging.DEBUG if os.environ.get("LOGLEVEL") == "debug" else logging.INFO
    root.setLevel(loglevel)
    color_logger = logging.StreamHandler(sys.stdout)
    color_logger.setLevel(loglevel)
    color_logger.setFormatter(CustomFormatter())
    root.addHandler(color_logger)

    builder_tool = os.environ.get("BUILD_SYSTEM")
    if not builder_tool:
        logging.info("No build system specified, inferring from pyproject.")
        backend = None
        with open("pyproject.toml", "rt", encoding="UTF-8") as handle:
            for line in handle.readlines():
                if "build-backend" in line:
                    _, backend = line.split("=", 1)
                    backend = backend.strip()
                    break
        if not backend:
            raise RuntimeError("Could not determine build system")
        for builder in KNOWN_BUILDERS:
            if builder in backend:
                builder_tool = builder
                logging.info("Using inferred build system '%s'", builder_tool)
                break
        if not builder_tool:
            backend = backend.split(".")[0]
            logging.warning("Using untested backend '%s'", backend)
            builder_tool = backend
    else:
        logging.info("Using specified build system '%s'", builder_tool)

    runner = BuildScript()
    release_branch, version = runner.branching_model()
    logging.info("Using version %s (release branch: %r)", version, release_branch)

    base_path = runner.find_python()
    if base_path:
        logging.info("Using discovered python at %s", base_path)

    # See what we're running
    runner.add([base_path + "python3", "--version"], show_output=True)

    # Upgrade pip
    runner.add(
        [
            base_path + "python3",
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "setuptools",
            "wheel",
        ]
    )

    # We can just install it in our local environment, since we're not loading
    # any script dependencies.
    if builder_tool == "pdm":
        with open("pdm.toml", "wt", encoding="utf-8") as handle:
            handle.write("check_update = false\n")

    # Update the version
    lines = []
    with open("pyproject.toml", mode="rt", encoding="utf8") as handle:
        for line in handle:
            # Brute force, should probably use a semantic version match or soemthing
            if line.startswith("version"):
                line = f'version = "{version}"\n'
            lines.append(line)
    with open("pyproject.toml", mode="wt", encoding="utf8") as handle:
        handle.write("".join(lines))

    build_name = os.environ.get("BLD_NAME", "")
    if build_name:
        package_name = build_name.replace("-", "_")
        for path in (package_name, f"src/{package_name}"):
            version_path = os.path.join(path, "_version.py")
            if os.path.exists(version_path):
                with open(version_path, "wt", encoding="UTF-8") as handle:
                    handle.write(f'__version__="{version}"\n')
                    handle.write(
                        '__commit__="{}"\n'.format(
                            os.environ.get("BLD_SHORT_COMMIT_HASH")
                        )
                    )
                break

    build_cmd = [base_path + "python3", "-m", "build"]
    show_build_output = loglevel == logging.DEBUG
    litellm_pyproject = os.path.join("src", "litellm", "pyproject.toml")
    if os.path.exists(litellm_pyproject):
        # Temporary compatibility wheel; remove once the upstream package supports Python 3.14.
        runner.add(
            [
                base_path + "python3",
                "-m",
                "build",
                "src/litellm",
                "--wheel",
                "--outdir",
                "dist",
            ],
            show_output=show_build_output,
        )
    if show_build_output:
        build_cmd.append("-vv")
    runner.add(build_cmd, show_output=show_build_output)

    runner.execute()
    if os.environ.get("PYTHON2_RELEASE") == "Y":
        for file in os.listdir("dist"):
            if "py2.py3" in file:
                os.rename(
                    os.path.join("dist", file),
                    os.path.join("dist", file.replace("py2.py3", "py2")),
                )

    repo_name = None
    if release_branch:
        repo_name = os.environ.get("RELEASE_REPOSITORY")
    else:
        repo_name = os.environ.get("DEVELOP_REPOSITORY")
    logging.info(f"Using repo {repo_name}")
    runner.run_command(["mv", "dist", repo_name])


if __name__ == "__main__":
    sys.exit(main())
