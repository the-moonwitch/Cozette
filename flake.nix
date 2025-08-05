{
  description = "A bitmap programming font optimized for coziness";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixos-24.11";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      python-with-packages = pkgs.python312.withPackages (ppkgs:
        with ppkgs; [
          numpy
          pillow
          fonttools
          crayons
          gitpython
          setuptools
          pip
        ]);
    in {
      devShells = {
        default = pkgs.mkShellNoCC {
          packages = with pkgs; [
            # BitsNPicas GUI wrapped with java
            self.packages.${system}.bitsnpicas-bin
            # FontForge GUI
            fontforge-gtk
            # Python tools
            python312Packages.black
            python312Packages.mypy
            python312Packages.isort
            python312Packages.ruff
            python-with-packages
          ];
        };
      };
      packages = rec {
        # BitsNPicas needs to be fetched here since `nix build` is sandboxed
        # and does not have internet access
        bitsnpicas = pkgs.stdenvNoCC.mkDerivation rec {
          pname = "bitsnpicas";
          version = "2.1";
          src = pkgs.fetchFromGitHub {
            owner = "kreativekorp";
            repo = "bitsnpicas";
            rev = "v${version}";
            hash = "sha256-hw7UuzesqpmnTjgpfikAIYyY70ni7BxjaUtHAPEdkXI=";
          };
          buildInputs = [pkgs.zulu23 pkgs.zip];
          buildPhase = ''
            cd main/java/BitsNPicas
            make
          '';
          installPhase = ''
            mkdir -p $out
            cp BitsNPicas.jar $out
            cp KeyEdit.jar $out
            cp MapEdit.jar $out
          '';
        };

        # Shell script to run the BitsNPicas GUI
        bitsnpicas-bin = pkgs.writeShellScriptBin "bitsnpicas" ''
          ${pkgs.zulu23}/bin/java -jar ${bitsnpicas}/BitsNPicas.jar $@
        '';

        # Derivation to build and install cozette
        cozette = pkgs.stdenvNoCC.mkDerivation {
          pname = "cozette";
          version = "1.28.0";

          src = ./.;

          buildInputs = with pkgs; [
            python-with-packages
            fontforge
            zulu23
          ];

          configurePhase = ''
            mkdir -p deps
            cp ${bitsnpicas}/BitsNPicas.jar deps/
          '';

          buildPhase = ''
            patchShebangs bitsnpicas.sh
            python3 build.py fonts
          '';

          installPhase = ''
            runHook preInstall

            cd build

            install -Dm644 *.ttf -t $out/share/fonts/truetype
            install -Dm644 *.otf -t $out/share/fonts/opentype
            install -Dm644 *.bdf -t $out/share/fonts/misc
            install -Dm644 *.otb -t $out/share/fonts/misc
            install -Dm644 *.woff -t $out/share/fonts/woff
            install -Dm644 *.woff2 -t $out/share/fonts/woff2

            runHook postInstall
          '';
        };
        default = cozette;
      };
    });
}
