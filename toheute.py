#!/usr/bin/env -S uv run --quiet --no-project

# ///script
# requires-python = ">=3.12"
# dependencies = [
#    "click>=8.2.0",
#    "gitpython>=3.1.44",
#    "rich>=13.9.4",
# ]
# ///

import contextlib
import dataclasses
import subprocess
import sys
from pathlib import Path
from subprocess import CompletedProcess
from typing import Literal, NoReturn

import click
from git import InvalidGitRepositoryError, Repo
from rich.console import Console
from rich.prompt import Prompt
from rich.padding import Padding, PaddingDimensions
from rich.status import Status

PATH_PREFIX_BLOCK_LIST = (".werks", "bin", "packages", "tests")
PATH_PREFIX_ALLOW_LIST = ("packages/cmk-frontend",)


type PadVariant = Literal["extra"] | None
type StyleVariant = Literal["success", "danger", "warn", "muted"] | None


@click.command()
@click.option("--no-reload", is_flag=True, help="Don't reload services.")
@click.option("--full-reload", is_flag=True, help="Force a full reload of services.")
def main(no_reload: bool, full_reload: bool) -> None:
    console = AppConsole()

    site_name = SiteManager(console).select_site()

    repo = GitRepository(console)
    commit = repo.get_last_commit()
    repo.print_commit_info(commit)

    if not (valid_paths := commit.get_valid_paths()):
        console.exit("No paths available to copy.", style="warn")

    if not console.confirm():
        console.exit("No paths to copy.", style="success")

    with console.in_progress("Syncing files"):
        FileManager(site_name, valid_paths, console).sync()

    if no_reload and not full_reload:
        console.exit("Not reloading services. Done :)", style="success")

    site = SiteController(site_name, console)
    with console.in_progress("Reloading services"):
        site.restart_checkmk()
        if full_reload or commit.has_gui_change():
            site.restart_apache()
            site.restart_ui_scheduler()


class AppConsole:
    def __init__(self) -> None:
        self._console = Console()
        self._console.clear()

    def heading(self, msg: str) -> None:
        self._console.rule(msg)

    def print(
        self, msg: str, *, pad: PadVariant = None, style: StyleVariant = None
    ) -> None:
        pad_ = self._get_padding_value(pad)
        style_ = self._get_style_value(style)
        self._console.print(Padding(msg, pad=pad_), style=style_)

    def exit(self, msg: str, *, style: StyleVariant) -> NoReturn:
        exit_code = 1 if style == "danger" else 0
        self.print(msg, style=style, pad="extra")
        sys.exit(exit_code)

    def prompt(self, msg: str, *, default: str, choices: list[str]) -> str:
        m = f"  {msg}"  # unfortunately, can't apply padding to Prompt.ask.
        return Prompt.ask(m, console=self._console, default=default, choices=choices)

    def confirm(self) -> bool:
        return self.prompt("Proceed", default="y", choices=["y", "n"]) == "y"

    def in_progress(self, label: str) -> Status:
        self._console.print()
        return self._console.status(f"[blue]{label}...", spinner="dots3")

    def _get_padding_value(self, variant: PadVariant) -> PaddingDimensions:
        match variant:
            case "extra":
                return (1, 2)
            case _:
                return (0, 0, 0, 2)

    def _get_style_value(self, variant: StyleVariant) -> str:
        match variant:
            case "success":
                return "green"
            case "danger":
                return "red"
            case "warn":
                return "yellow"
            case "muted":
                return "gray50"
            case _:
                return "black"


class SiteManager:
    def __init__(self, console: AppConsole) -> None:
        self._console = console

    def select_site(self) -> str:
        if len(sites := self.get_site_names()) == 1:
            return sites[0]

        mapping = {site: str(idx) for idx, site in enumerate(sites, 1)}
        default = self.get_site_from_environment()

        self._print_options(mapping, default)

        return self._parse_selection(
            sites, mapping.get(default, "1"), list(mapping.values())
        )

    @staticmethod
    def get_site_names() -> list[str]:
        raw_sites = subprocess.check_output(["omd", "sites", "--bare"]).decode("utf-8")
        return [site for site in raw_sites.rstrip("\n").split("\n")]

    @staticmethod
    def get_site_from_environment() -> str:
        if not (site_path := Path(".site")).exists():
            return ""
        return site_path.read_text().strip()

    def _print_options(self, mapping: dict[str, str], default: str = "") -> None:
        self._console.heading("Select a site")
        self._console.print("Available sites:", pad="extra")
        for site, idx in mapping.items():
            style = None if site == default else "muted"
            self._console.print(f"  {idx:<3}{site}", style=style)
        self._console.print("")

    def _parse_selection(
        self, sites: list[str], default: str, choices: list[str]
    ) -> str:
        match choice := self._console.prompt(
            "Select", default=default, choices=choices
        ):
            case "q":
                self._console.exit("See you soon :)", style="success")
            case _:
                return sites[int(choice) - 1]


@dataclasses.dataclass
class Commit:
    author: str
    time: str
    message: str
    filepaths: list[Path]

    def get_valid_paths(self) -> list[Path]:
        return [fp for fp in self.filepaths if self._is_valid_path(fp)]

    def get_invalid_paths(self) -> list[Path]:
        return [fp for fp in self.filepaths if not self._is_valid_path(fp)]

    def has_gui_change(self) -> bool:
        return any(str(fpath).startswith("cmk/gui") for fpath in self.get_valid_paths())

    def _is_valid_path(self, fpath: Path) -> bool:
        in_block_list = str(fpath).startswith(PATH_PREFIX_BLOCK_LIST)
        in_allow_list = str(fpath).startswith(PATH_PREFIX_ALLOW_LIST)
        return not in_block_list or in_allow_list


class GitRepository:
    def __init__(self, console: AppConsole) -> None:
        self._console = console
        self._git = self._load_git_repository()

    def get_last_commit(self) -> Commit:
        return Commit(
            author=self._git.head.commit.author.name,
            time=self._git.head.commit.committed_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            message=self._git.head.commit.message,
            filepaths=[Path(f) for f in self._git.head.commit.stats.files.keys()],
        )

    def print_commit_info(self, commit: Commit) -> None:
        self._console.heading("Last commit")
        self._console.print(f"{commit.author} ({commit.time})", pad="extra")
        self._console.print(f"{commit.message:.>30}", style="muted")

        if not commit.filepaths:
            self._console.exit("No changed files.", style="success")

        self._console.heading("Sync files")

        self._console.print("The following files will be copied:", pad="extra")
        for fp in commit.get_valid_paths():
            self._console.print(str(fp), style="muted")

        if invalid_paths := commit.get_invalid_paths():
            self._console.print("Unable to sync the following files:", pad="extra")
            for fp in invalid_paths:
                self._console.print(str(fp), style="warn")
        self._console.print("")

    def _load_git_repository(self) -> Repo:
        try:
            return Repo(search_parent_directories=True)
        except InvalidGitRepositoryError:
            self._console.exit("Make sure you're in a git repository.", style="danger")


class FileManager:
    def __init__(self, site: str, paths: list[Path], console: AppConsole) -> None:
        self._site = site
        self._paths = paths
        self._console = console

    def sync(self) -> None:
        for path in self._paths:
            site_path = self._get_site_path(path)
            result = self._copy(path, site_path)
            self._print_result(site_path, result)

    def _get_site_path(self, fpath: Path) -> Path:
        match fpath:
            case path if str(path).startswith("active_checks"):
                return Path(f"/omd/sites/{self._site}/lib/nagios/plugins") / fpath.name
            case path if str(path).startswith("packages/cmk-frontend/src"):
                rp = path.relative_to("packages/cmk-frontend/src")
                return Path(f"/omd/sites/{self._site}/share/check_mk/web/htdocs") / rp
            case _:
                return Path(f"/omd/sites/{self._site}/lib/python3") / fpath

    def _copy(self, src_path: Path, site_path: Path) -> CompletedProcess:
        args = ["sudo", "cp", "-R", src_path, site_path]
        return subprocess.run(args, capture_output=True, text=True)

    def _print_result(self, path: Path, result: CompletedProcess) -> None:
        name = str(path)
        if result.returncode != 0:
            self._console.print(f"ERROR: {result.stderr}", style="danger")
            self._console.print(f"𐄂 {name}")
        else:
            self._console.print(f"✓ {name}")


@dataclasses.dataclass
class SiteController:
    def __init__(self, site: str, console: AppConsole) -> None:
        self._site = site
        self._console = console

    def restart_checkmk(self) -> None:
        result = self._execute("cmk -R")
        self._print_result("Restart Checkmk", result)

    def restart_apache(self) -> None:
        result = self._execute("omd reload apache")
        self._print_result("Restart Apache", result)

    def restart_ui_scheduler(self) -> None:
        result = self._execute("omd restart ui-job-scheduler")
        self._print_result("Restart UI Job Scheduler", result)

    def _execute(self, cmd: str) -> CompletedProcess:
        reload_cmd = f"sudo --login -u {self._site} -- {cmd}"
        return subprocess.run(reload_cmd.split(), capture_output=True, text=True)

    def _print_result(self, heading: str, result: CompletedProcess) -> None:
        self._console.heading(heading)
        if result.returncode != 0:
            self._console.print(f"ERROR: {result.stderr}", style="danger")
        self._console.print(result.stdout, style="muted")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        main()
