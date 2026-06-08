{
  description = "A bitmap programming font optimized for coziness";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixos-25.11";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        inherit (pkgs) lib;
      in
      {
        devShells = {
          default = pkgs.mkShellNoCC {
            packages = with pkgs; [
              # FontForge GUI
              fontforge-gtk
              # Python tools
              python312Packages.black
              python312Packages.mypy
              python312Packages.isort
              python312Packages.ruff
            ];
          };
        };
        packages = rec {
          # Derivation to build and install cozette
          cozette = pkgs.stdenvNoCC.mkDerivation {
            pname = "cozette";
            version =
              let
                sfdLines = lib.strings.splitString "\n" (builtins.readFile ./Cozette/Cozette.sfd);
                sfdVersionLine = lib.lists.findFirst (l: lib.strings.hasPrefix "Version: " l) null sfdLines;
                sfdVersion =
                  if sfdVersionLine != null then lib.strings.removePrefix "Version: " sfdVersionLine else "0.00";
                majorRest = lib.strings.splitString "." sfdVersion;
                major = builtins.elemAt majorRest 0;
                minorPatch = builtins.elemAt majorRest 1;
                minor = builtins.substring 0 2 minorPatch;
                patch = builtins.substring 2 1 minorPatch;
              in
              "${major}.${minor}.${patch}";

            src = ./.;

            buildInputs = with pkgs; [
              (pkgs.python312.withPackages (
                ppkgs: with ppkgs; [
                  numpy
                  pillow
                  fonttools
                  crayons
                  gitpython
                  setuptools
                  pip
                ]
              ))
              fontforge
              bitsnpicas
            ];

            postPatch = ''
              substituteInPlace build.py --replace-fail \
                'bitsnpicas.sh' '${lib.getExe pkgs.bitsnpicas}'
            '';

            buildPhase = ''
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
      }
    );
}
