{ pkgs, ... }:

{
  # ADR-001: devenv configuration for torproxy
  languages.python = {
    enable = true;
    venv.enable = true;
  };

  packages = [
    pkgs.git
    pkgs.ruff
    pkgs.shellcheck
  ];

  pre-commit.hooks = {
    ruff.enable = true;
    shellcheck.enable = true;
  };
}
