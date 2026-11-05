{
  description = "novelty-check: an agent skill that checks whether a CS research idea has been done";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      # For working on the skill. Users of the skill need only python3.
      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [
            pkgs.python3
            pkgs.ruff
            pkgs.poppler-utils
          ];
        };
      });

      checks = forAll (pkgs: {
        tests =
          pkgs.runCommand "novelty-check-tests"
            {
              nativeBuildInputs = [ pkgs.python3 ];
            }
            ''
              cp -r ${self} src && chmod -R u+w src && cd src
              export HOME=$TMPDIR
              python3 -m unittest discover -s tests -t .
              touch $out
            '';
        lint =
          pkgs.runCommand "novelty-check-lint"
            {
              nativeBuildInputs = [ pkgs.ruff ];
            }
            ''
              cd ${self}
              ruff check --no-cache .
              ruff format --no-cache --check .
              touch $out
            '';
      });

      formatter = forAll (pkgs: pkgs.nixfmt);
    };
}
