#!/usr/bin/env -S uv run --quiet --no-project

# ///script
# requires-python = ">=3.12"
# dependencies = [
#    "gitpython>=3.1.44",
#    "rich>=13.9.4",
# ]
# ///

import dataclasses
import subprocess
import sys
from pathlib import Path
from subprocess import CompletedProcess
from typing import Literal, NoReturn, Self

from git import GitConfigParser, InvalidGitRepositoryError, Repo
from rich.console import Console
from rich.prompt import Prompt
from rich.status import Status


def main():
    console = AppConsole()

    try:
        repo: Repo = Repo(search_parent_directories=True)
    except InvalidGitRepositoryError:
        console.exit("Make sure you're in a check_mk git repository.", variant="danger")

    if (repo_dir := repo.working_tree_dir) is None:
        console.exit("Repository directory is empty.", variant="danger")

    sites = get_site_names()
    site = select_site(sites=sites, console=console)

    last_commit = LastCommit.from_repo(repo)
    username = read_username_from_git_config(repo)
    console.print_commit_info(site, last_commit, username)

    if console.prompt_user("Press 'y' to copy") != "y":
        console.exit("Nothing to do...", variant="info")

    with console.progress_spinner("Copying files"):
        for fpath in last_commit.get_valid_paths():
            src_path = repo_dir / fpath
            site_path = get_site_path(site, fpath)
            result = copy_file(src_path, site_path)
            console.print_copy_result(str(site_path), result)

    with console.progress_spinner("Reloading services"):
        site_result = execute_site_command(site, "cmk -R")
        console.print_reload_result("CMK restart", site_result)

        if last_commit.has_gui_change():
            gui_result = execute_site_command(site, "omd reload apache")
            console.print_reload_result("Apache reload", gui_result)

            ui_scheduler_result = execute_site_command(site, "omd restart ui-job-scheduler")
            console.print_reload_result("UI job scheduler restart", ui_scheduler_result)


@dataclasses.dataclass
class LastCommit:
    author: str
    time: str
    message: str
    filepaths: list[Path]

    @classmethod
    def from_repo(cls, repo: Repo) -> Self:
        return cls(
            author=repo.head.commit.author.name,
            time=repo.head.commit.committed_datetime.strftime("%d/%m/%Y, %H:%M:%S"),
            message=repo.head.commit.message,
            filepaths=[Path(f) for f in repo.head.commit.stats.files.keys()],
        )

    def get_valid_paths(self) -> list[Path]:
        return [fp for fp in self.filepaths if self._is_valid_path(fp)]

    def get_invalid_paths(self) -> list[Path]:
        return [fp for fp in self.filepaths if not self._is_valid_path(fp)]

    def has_gui_change(self) -> bool:
        return any(str(fpath).startswith("cmk/gui") for fpath in self.get_valid_paths())

    def _is_valid_path(self, fpath: Path) -> bool:
        return not str(fpath).startswith((".werks", "bin", "packages", "tests"))


Variant = Literal["success", "danger", "info"]


class AppConsole:
    def __init__(self) -> None:
        self.console = Console()
        self.console.clear()

    def exit(self, msg: str, *, variant: Variant) -> NoReturn:
        match variant:
            case "success":
                style, code = "green", 0
            case "danger":
                style, code = "red", 1
            case "info":
                style, code = "blue", 0

        self.console.print(msg, style=style, new_line_start=True)
        sys.exit(code)

    def prompt_user(self, msg: str) -> str:
        return Prompt.ask(msg, console=self.console)

    def progress_spinner(self, label: str) -> Status:
        self.console.print()
        return self.console.status(f"[blue]{label}...", spinner="monkey")

    def print_sites_info(self, sites: list[str]) -> None:
        self.console.rule("Select a site")
        self.console.print("Available sites:", new_line_start=True, end="\n\n")
        for n, site in enumerate(sites, 1):
            self.console.print(f"  {n:<3}{site}")
        self.console.print("  Enter 'q' to quit.", end="\n\n")

    def print_commit_info(self, site: str, commit: LastCommit, username: str) -> None:
        self.console.rule("Last commit")
        self.console.print(
            f"\n{commit.author} ({commit.time})\n",
            style="black" if commit.author == username else "red",
        )
        self.console.print(f"{commit.message:.>30}", style="italic")

        if not commit.filepaths:
            self.exit("No changed files.", variant="info")

        self.console.rule("Detected file changes")
        self.console.print(f"\nUpdate the following files on site '{site}':\n")
        for fp in commit.get_valid_paths():
            self.console.print(f"  {Path(f'/omd/sites/{site}/lib/python3') / fp}")

        if invalid_paths := commit.get_invalid_paths():
            self.console.print("\nThe following paths cannot be copied:\n")
            for fp in invalid_paths:
                self.console.print(f"  {fp}", style="yellow")

        self.console.print()

    def print_copy_result(self, name: str, result: CompletedProcess) -> None:
        if result.returncode != 0:
            self.console.print(f"\n Error copying file: {result.stderr}", style="red")
            self.console.print(f"  '{name}' ❌", style="red")
        else:
            self.console.print(f"  '{name}' ✔️", style="green")

    def print_reload_result(self, label: str, result: CompletedProcess) -> None:
        self.console.rule(label)
        if result.returncode != 0:
            self.console.print(f"❌  {result.stderr}", style="red")
        self.console.print(result.stdout, style="dim")


def get_site_names() -> list[str]:
    raw_sites = subprocess.check_output(["omd", "sites", "--bare"]).decode("utf-8")
    return [site for site in raw_sites.rstrip("\n").split("\n")]


def select_site(sites: list[str], console: AppConsole) -> str:
    if len(sites) == 1:
        return sites[0]

    console.print_sites_info(sites)
    choice = console.prompt_user("Select a site")

    if choice == "q":
        console.exit("See you soon :)", variant="success")

    if not choice.isdigit():
        console.exit("Invalid input.", variant="danger")

    site_number = int(choice)

    if site_number < 1 or site_number > len(sites):
        console.exit(f"Site number {site_number!r} is not available.", variant="danger")

    return sites[site_number - 1]


def read_username_from_git_config(repo: Repo) -> str:
    repo_config: GitConfigParser = repo.config_reader()
    username = repo_config.get_value(section="user", option="name")
    assert isinstance(username, str)
    return username

def get_site_path(site: str, fpath: Path) -> Path:
    match fpath:
        case path if str(path).startswith("active_checks"):
            return Path(f"/omd/sites/{site}/lib/nagios/plugins") / fpath.name
        case _:
            return Path(f"/omd/sites/{site}/lib/python3") / fpath

def copy_file(src_path: Path, site_path: Path) -> CompletedProcess:
    args = ["sudo", "cp", "-R", src_path, site_path]
    return subprocess.run(args, capture_output=True, text=True)


def execute_site_command(site: str, cmd: str) -> CompletedProcess:
    reload_cmd = f"sudo --login -u {site} -- {cmd}"
    return subprocess.run(reload_cmd.split(), capture_output=True, text=True)


if __name__ == "__main__":
    main()
