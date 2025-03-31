#!/usr/bin/env -S uv run --quiet --no-project

# ///script
# requires-python = ">=3.12"
# dependencies = [
#    "gitpython>=3.1.44",
#    "rich>=13.9.4",
#    "ruff>=0.11.2",
# ]
# ///

import subprocess
import sys
from pathlib import Path

from git import GitConfigParser, InvalidGitRepositoryError, PathLike, Repo
from rich.console import Console
from rich.prompt import Prompt


def get_sites() -> list[str]:
    raw_sites = subprocess.check_output(["omd", "sites", "--bare"]).decode("utf-8")
    return [site for site in raw_sites.rstrip("\n").split("\n")]


def get_site_from_user(sites: list[str], console: Console) -> str:
    if len(sites) == 1:
        return sites[0]

    console.print("\n")
    console.rule("Available sites")
    for n, site in enumerate(sites, 1):
        console.print(f"{n:<3}{site}")
    console.print("")
    console.print("Enter 'q' to quit.")
    console.print("")

    choice = Prompt.ask("Select a site", console=console)

    return get_site_from_choice(choice, sites, console)


def get_site_from_choice(choice: str, sites: list[str], console: Console) -> str:
    if choice == "q":
        sys.exit(0)

    if not choice.isdigit():
        console.print("Invalid input.", style="red")
        sys.exit(1)

    site_number = int(choice)

    if site_number < 1 or site_number > len(sites):
        console.print(f"Site number {site_number!r} is not available.", style="red")
        sys.exit(1)

    return sites[site_number - 1]


def check_last_commit(repo: Repo, console: Console) -> list[Path]:
    repo_config: GitConfigParser = repo.config_reader()
    git_username = repo_config.get_value(section="user", option="name")
    last_commit_time = repo.head.commit.committed_datetime.strftime(
        "%d/%m/%Y, %H:%M:%S"
    )
    last_commit_username = repo.head.commit.author.name
    last_commit_msg = repo.head.commit.message

    console.print(
        f"\nLast commit: {last_commit_username}\t{last_commit_time}\n\n{last_commit_msg:.>30}",
        style="green" if last_commit_username == git_username else "red",
    )
    return [
        Path(f)
        for f, _ in repo.head.commit.stats.files.items()
        if not str(f).startswith((".werks", "bin"))
    ]


def show_changed_files(site: str, changed_files: list[Path], console: Console) -> None:
    console.print(f" Update the following files on site '{site}'")
    for repo_file_path in changed_files:
        console.print(f"  '{Path(f'/omd/sites/{site}/lib/python3') / repo_file_path}'")
    console.print("\n")


def copy_files(
    site: str, changed_files: list[Path], repo_dir: Path, console: Console
) -> None:
    if (Prompt.ask(" Press Y to copy", console=console)) == "y":
        with console.status("[blue]Copying files...", spinner="monkey"):
            for repo_file_path in changed_files:
                changed_file_path = Path(repo_dir / repo_file_path)
                site_file_path = (
                    Path(f"/omd/sites/{site}/lib/python3") / repo_file_path
                )  # TODO: Some files don't map exactly the same as the repo
                result = subprocess.run(
                    ["sudo", "cp", "-R", changed_file_path, site_file_path],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    console.print(
                        f"\n Error copying file: {result.stderr}", style="red"
                    )
                    console.print(f"  '{site_file_path.name}' ❌", style="red")
                else:
                    console.print(f"  '{site_file_path.name}' ✔️", style="green")


def show_and_copy_files(
    site: str,
    changed_files: list[Path],
    repo_dir: PathLike | None,
    console: Console,
) -> None:
    if not changed_files:
        console.print("No changed files.", style="blue")
        return

    assert repo_dir is not None

    show_changed_files(
        site=site,
        changed_files=changed_files,
        console=console,
    )
    copy_files(
        site=site,
        changed_files=changed_files,
        repo_dir=Path(repo_dir),
        console=console,
    )


def main():
    console = Console()
    console.clear()

    try:
        repo: Repo = Repo(search_parent_directories=True)
        selected_site = get_site_from_user(sites=get_sites(), console=console)
        changed_files = check_last_commit(repo, console)
    except (InvalidGitRepositoryError, ValueError):
        console.print("\nMake sure you are in a check_mk git repository.", style="red")
    except KeyboardInterrupt:
        pass
    else:
        show_and_copy_files(
            site=selected_site,
            changed_files=changed_files,
            repo_dir=repo.working_tree_dir,
            console=console,
        )


if __name__ == "__main__":
    main()
