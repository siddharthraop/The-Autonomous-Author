import pathlib
import yaml

project = "natctl documentation"
extensions = ["myst_parser"]
myst_enable_extensions = ["substitution"]
myst_substitutions = yaml.safe_load(
    (pathlib.Path(__file__).parent / "substitutions.yml").read_text()
)
exclude_patterns = ["_build"]
html_theme = "alabaster"
