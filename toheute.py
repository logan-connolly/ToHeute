#!/usr/bin/env -S uv run --quiet --no-project

# ///script
# requires-python = ">=3.12"
# dependencies = [
#    "gitpython>=3.1.44",
#    "rich>=13.9.4",
#    "ruff>=0.11.2",
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

    if console.prompt_user(" Press 'y' to copy") != "y":
        console.exit("Nothing to do...", variant="info")

    with console.file_copying_progress():
        for fpath in last_commit.filepaths:
            src_path = repo_dir / fpath
            site_path = Path(f"/omd/sites/{site}/lib/python3") / fpath
            result = copy_file(src_path, site_path)
            console.print_copy_result(site_path.name, result)


@dataclasses.dataclass
class LastCommit:
    author: str
    time: str
    message: str
    filepaths: list[Path]

    @classmethod
    def from_repo(cls, repo: Repo) -> Self:
        filepaths = [
            Path(f)
            for f in repo.head.commit.stats.files.keys()
            if not str(f).startswith((".werks", "bin"))
        ]
        return cls(
            author=repo.head.commit.author.name,
            time=repo.head.commit.committed_datetime.strftime("%d/%m/%Y, %H:%M:%S"),
            message=repo.head.commit.message,
            filepaths=filepaths,
        )


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

    def print_sites_info(self, sites: list[str]) -> None:
        self.console.print("Available sites:", style="green", new_line_start=True, end="\n\n")
        for n, site in enumerate(sites, 1):
            self.console.print(f"  {n:<3}{site}")
        self.console.print("  Enter 'q' to quit.", new_line_start=True, end="\n\n")

    def print_commit_info(self, site: str, commit: LastCommit, username: str) -> None:
        msg = f"\nLast commit: {commit.author}\t{commit.time}\n\n{commit.message:.>30}"
        self.console.print(msg, style="green" if commit.author == username else "red")

        if not commit.filepaths:
            self.exit("No changed files.", variant="info")

        self.console.print(f" Update the following files on site '{site}'")
        for fp in commit.filepaths:
            self.console.print(f"  '{Path(f'/omd/sites/{site}/lib/python3') / fp}'")
        self.console.print()

    def file_copying_progress(self) -> Status:
        return self.console.status("[blue]Copying files...", spinner="monkey")

    def print_copy_result(self, name: str, result: CompletedProcess) -> None:
        if result.returncode != 0:
            self.console.print(f"\n Error copying file: {result.stderr}", style="red")
            self.console.print(f"  '{name}' ❌", style="red")
        else:
            self.console.print(f"  '{name}' ✔️", style="green")


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


def copy_file(src_path: Path, site_path: Path) -> CompletedProcess:
    args = ["sudo", "cp", "-R", src_path, site_path]
    return subprocess.run(args, capture_output=True, text=True)


if __name__ == "__main__":
    main()
