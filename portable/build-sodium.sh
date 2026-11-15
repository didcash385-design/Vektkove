#!/bin/bash
# Builds pinned, checksum-verified static libsodium libraries into deps/.
#   portable/build-sodium.sh mac                 universal macOS (x86_64 + arm64)
#   ZIG=/path/to/zig portable/build-sodium.sh linux-x64 | linux-aarch64 | windows-x64 | windows-arm64
set -eu
cd "$(dirname "$0")/.."
VERSION=1.0.20
SHA256=ebb65ef6ca439333c2bb41a0c1990587288da07f6c7fd07cb3a18cc18d30ce19
ARCHIVE="deps/libsodium-$VERSION.tar.gz"
TARGET="${1:?usage: build-sodium.sh mac|linux-x64|linux-aarch64|windows-x64|windows-arm64}"
mkdir -p deps
if [ ! -f "$ARCHIVE" ]; then
  curl -fL --retry 2 -o "$ARCHIVE" "https://download.libsodium.org/libsodium/releases/libsodium-$VERSION.tar.gz"
fi
echo "$SHA256  $ARCHIVE" | shasum -a 256 -c - >/dev/null || { echo "libsodium checksum mismatch" >&2; rm -f "$ARCHIVE"; exit 1; }

PREFIX="$PWD/deps/sodium-$TARGET"
[ -f "$PREFIX/lib/libsodium.a" ] && { echo "deps/sodium-$TARGET already built"; exit 0; }
[ ! -e "$PREFIX" ] || { echo "Incomplete dependency directory exists: $PREFIX" >&2; exit 1; }
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
STAGE="$WORK/install"   # autotools cannot install into paths containing spaces
tar -xzf "$ARCHIVE" -C "$WORK" --strip-components=1
cd "$WORK"

# libtool mistakes Zig's compiler for MSVC on Windows and looks for a nonexistent `lib` tool,
# so compile libsodium's portable C sources directly into a static archive instead.
if [ "$TARGET" = windows-x64 ] || [ "$TARGET" = windows-arm64 ]; then
  ZIG="${ZIG:?set ZIG=/path/to/zig}"
  case "$TARGET" in
    windows-x64) zig_target=x86_64-windows-gnu ;;
    windows-arm64) zig_target=aarch64-windows-gnu ;;
  esac
  cp builds/msvc/version.h src/libsodium/include/sodium/version.h
  mkdir -p obj
  for f in $(find src/libsodium -name '*.c'); do
    o="obj/$(echo "$f" | tr '/' '_').o"
    "$ZIG" cc -target "$zig_target" -O2 -DSODIUM_STATIC -DCONFIGURED=1 -DNATIVE_LITTLE_ENDIAN \
      -Isrc/libsodium/include -Isrc/libsodium/include/sodium -c "$f" -o "$o" 2>"$WORK/cc.log" \
      || { tail -20 "$WORK/cc.log" >&2; echo "failed compiling $f" >&2; exit 1; }
  done
  "$ZIG" ar rcs libsodium.a obj/*.o
  mkdir -p "$STAGE/lib" "$STAGE/include"
  cp libsodium.a "$STAGE/lib/"
  cp -R src/libsodium/include/sodium.h src/libsodium/include/sodium "$STAGE/include/"
  mkdir -p "$PREFIX"
  cp -R "$STAGE/include" "$STAGE/lib" "$PREFIX/"
  echo "built deps/sodium-$TARGET"
  exit 0
fi

case "$TARGET" in
  mac)
    CC=clang CFLAGS='-arch x86_64 -arch arm64 -mmacosx-version-min=11.0' \
      ./configure --disable-shared --enable-static --prefix="$STAGE" >/dev/null ;;
  linux-x64|linux-aarch64|windows-x64)
    ZIG="${ZIG:?set ZIG=/path/to/zig}"
    case "$TARGET" in
      linux-x64)     zig_target=x86_64-linux-musl;   host=x86_64-linux-musl ;;
      linux-aarch64) zig_target=aarch64-linux-musl;  host=aarch64-linux-musl ;;
      windows-x64)   zig_target=x86_64-windows-gnu;  host=x86_64-w64-mingw32 ;;
    esac
    CC="$ZIG cc -target $zig_target" AR="$ZIG ar" RANLIB="$ZIG ranlib" \
      ./configure --host="$host" --disable-shared --enable-static --prefix="$STAGE" >/dev/null ;;
  *) echo "unknown target $TARGET" >&2; exit 1 ;;
esac
make -j4 >"$WORK/make.log" 2>&1 || { tail -30 "$WORK/make.log" >&2; exit 1; }
make install >"$WORK/install.log" 2>&1 || { tail -30 "$WORK/install.log" >&2; exit 1; }
mkdir -p "$PREFIX"
cp -R "$STAGE/include" "$STAGE/lib" "$PREFIX/"
echo "built deps/sodium-$TARGET"
