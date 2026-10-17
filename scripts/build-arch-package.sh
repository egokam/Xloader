#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
project_version=0.1.0
xtool_version=1.22.2
machine_arch=$(uname -m)

case "$machine_arch" in
    x86_64)
        xtool_asset_arch=x86_64
        xtool_sha256=e3176cdf861f58b7f135c755c7bfaec92d0568ef826027b4e5e3d82b3219ddfe
        ;;
    aarch64)
        xtool_asset_arch=aarch64
        xtool_sha256=a42962f19874205ddd807ee4f97687fc83ddc9be176a8b1122a94af3de58d990
        ;;
    *)
        printf 'Unsupported build architecture: %s\n' "$machine_arch" >&2
        exit 1
        ;;
esac

for required_tool in makepkg curl sha256sum tar; do
    if ! command -v "$required_tool" >/dev/null 2>&1; then
        printf 'Missing build tool: %s\n' "$required_tool" >&2
        exit 1
    fi
done

if [ "$(id -u)" -eq 0 ]; then
    printf 'Run this package build as a regular user, not as root.\n' >&2
    exit 1
fi

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/xloader-package.XXXXXX")
trap 'rm -rf "$work_dir"' EXIT HUP INT TERM

source_root="$work_dir/source"
mkdir -p "$source_root" "$work_dir/pkgbuild"
cp -R "$repo_root/xloader" "$source_root/xloader"
find "$source_root/xloader" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$source_root/xloader" -type f -name '*.pyc' -delete
mkdir -p "$source_root/licenses" "$source_root/packaging/arch"
cp "$repo_root/README.md" "$source_root/README.md"
cp "$repo_root/licenses/xtool-LICENSE.md" "$source_root/licenses/xtool-LICENSE.md"
cp "$repo_root/packaging/arch/xloader" "$source_root/packaging/arch/xloader"
cp "$repo_root/packaging/arch/xloader.desktop" "$source_root/packaging/arch/xloader.desktop"
chmod 755 "$source_root/packaging/arch/xloader"

source_archive="$work_dir/xloader-source.tar.gz"
tar --sort=name --mtime='UTC 2026-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "$source_archive" -C "$source_root" .
source_sha256=$(sha256sum "$source_archive" | awk '{print $1}')
xtool_url="https://github.com/xtool-org/xtool/releases/download/$xtool_version/xtool-$xtool_asset_arch.AppImage"

cat > "$work_dir/pkgbuild/PKGBUILD" <<EOF
pkgname=xloader
pkgver=$project_version
pkgrel=1
pkgdesc='Install and refresh iPhone apps with a bundled signing engine'
arch=('$machine_arch')
url='https://github.com/egokam/Xloader'
license=('custom')
depends=('gtk4>=4.10' 'python' 'python-gobject' 'libimobiledevice' 'usbmuxd')
options=('!strip')
source=(
    "xloader-source.tar.gz::file://$source_archive"
    "xtool::$xtool_url"
)
sha256sums=(
    '$source_sha256'
    '$xtool_sha256'
)

package() {
    install -d "\$pkgdir/usr/lib/xloader"
    tar -xzf "\$srcdir/xloader-source.tar.gz" -C "\$pkgdir/usr/lib/xloader"
    install -Dm755 "\$srcdir/xtool" "\$pkgdir/usr/lib/xloader/xloader/vendor/xtool"
    install -Dm755 "\$pkgdir/usr/lib/xloader/packaging/arch/xloader" "\$pkgdir/usr/bin/xloader"
    install -Dm644 "\$pkgdir/usr/lib/xloader/packaging/arch/xloader.desktop" \\
        "\$pkgdir/usr/share/applications/xloader.desktop"
    install -Dm644 "\$pkgdir/usr/lib/xloader/licenses/xtool-LICENSE.md" \\
        "\$pkgdir/usr/share/licenses/xloader/xtool-LICENSE.md"
    rm -rf "\$pkgdir/usr/lib/xloader/packaging" "\$pkgdir/usr/lib/xloader/licenses"
}
EOF

mkdir -p "$repo_root/dist"
(
    cd "$work_dir/pkgbuild"
    makepkg --force --cleanbuild --clean --nodeps --noconfirm
)

built_package="$work_dir/pkgbuild/xloader-$project_version-1-$machine_arch.pkg.tar.zst"
if [ ! -f "$built_package" ]; then
    printf 'Package build completed without the expected artifact: %s\n' "$built_package" >&2
    exit 1
fi
package_path="$repo_root/dist/$(basename "$built_package")"
mv "$built_package" "$package_path"

printf '\nBuilt package: %s\n' "$package_path"
printf 'Bundled xtool: %s (%s)\n' "$xtool_version" "$xtool_asset_arch"
