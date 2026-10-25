"""Small wrappers around git, so every tool reads the same revisions."""
import subprocess


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def show(repo, rev, path):
    """File content at a revision, or None when the file does not exist there."""
    r = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def resolve(repo, rev):
    return git(repo, "rev-parse", rev).strip()
