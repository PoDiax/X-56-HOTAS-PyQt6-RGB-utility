# Maintainer: PoDiax <pd@pdx.ovh>

_pkgname=x56linux
pkgname=x56linux-git
pkgver=0.0.0
pkgrel=1
pkgdesc="Saitek/Logitech X-56 HOTAS PyQt6 RGB utility"
arch=('x86_64')
url="https://github.com/PoDix/x56-rgb-utility"
license=('MIT')
depends=(
  'libusb'
  'python'
  'python-pyqt6'
  'python-pyusb'
)
makedepends=(
  'git'
)
optdepends=(
  'polkit: pkexec support for guided udev rule install from GUI'
)
provides=('x56linux')
conflicts=('x56linux')
source=(
  "git+https://github.com/PoDix/x56-rgb-utility.git"
  "x56gui-launcher"
  "x56gui.desktop"
)
sha256sums=('SKIP' 'SKIP' 'SKIP')

pkgver() {
  cd "$srcdir/$_pkgname"
  printf "r%s.%s" "$(git rev-list --count HEAD)" "$(git rev-parse --short HEAD)"
}

package() {
  cd "$srcdir/$_pkgname"

  install -Dm755 "$srcdir/x56gui-launcher" "$pkgdir/usr/bin/x56gui"

  local pyver
  pyver="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  install -d "$pkgdir/usr/lib/python${pyver}/site-packages/x56gui"
  cp -a x56gui/*.py "$pkgdir/usr/lib/python${pyver}/site-packages/x56gui/"

  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
  install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"

  install -Dm644 "$srcdir/x56gui.desktop" "$pkgdir/usr/share/applications/x56gui.desktop"
}
