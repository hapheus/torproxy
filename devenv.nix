{ pkgs, ... }:

{
  languages.python = {
    enable = true;
    venv.enable = true;
    uv.enable = true;
  };

  packages = [
    pkgs.git
    pkgs.uv
    pkgs.shellcheck
    pkgs.actionlint
  ];

  enterShell = ''
    uv sync --active --frozen --extra dev
  '';
}
