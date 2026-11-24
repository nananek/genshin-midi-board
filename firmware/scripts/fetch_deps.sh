#!/usr/bin/env sh
# ---------------------------------------------------------------------------
#  ビルドに必要な外部ライブラリを firmware/lib/ 以下へ取得する。
#    - upstream hathach/tinyusb (MIDI ホスト対応版) … SDK 同梱版は非対応
#    - sekigon-gonnoc/Pico-PIO-USB
#  再現性のためタグ / コミットを固定している。
# ---------------------------------------------------------------------------
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$ROOT/lib"
mkdir -p "$LIB"

# --- バージョン固定 ---
TINYUSB_TAG="0.20.0"                                      # idx ベース tuh_midi API を含む最初のタグ
TINYUSB_COMMIT="3af1bec1a9161ee8dec29487831f7ac7ade9e189" # 0.20.0 の検証済みコミット
PIO_USB_REF="main"                                        # コミット取得用のリモート参照
PIO_USB_COMMIT="a5a2f5ae91988449ba576ec9d237e806d5cd4416"  # 検証済みコミット

clone() {
    url="$1"; dst="$2"; ref="$3"
    if [ -d "$dst/.git" ]; then
        echo "== already present: $dst (skip)"
        return
    fi
    echo "== cloning $url @ $ref"
    git clone --depth 1 --branch "$ref" "$url" "$dst"
}

clone "https://github.com/hathach/tinyusb.git"             "$LIB/tinyusb"       "$TINYUSB_TAG"
clone "https://github.com/sekigon-gonnoc/Pico-PIO-USB.git" "$LIB/Pico-PIO-USB" "$PIO_USB_REF"

# TinyUSB を可変タグから不変コミットへ固定する
if [ -n "$TINYUSB_COMMIT" ]; then
    echo "== pinning TinyUSB to $TINYUSB_COMMIT"
    ( cd "$LIB/tinyusb" && git fetch --depth 1 origin "$TINYUSB_COMMIT" && git checkout --detach "$TINYUSB_COMMIT" )
fi

# Pico-PIO-USB を検証済みコミットに固定する
if [ -n "$PIO_USB_COMMIT" ]; then
    echo "== pinning Pico-PIO-USB to $PIO_USB_COMMIT"
    ( cd "$LIB/Pico-PIO-USB" && git fetch --depth 1 origin "$PIO_USB_COMMIT" && git checkout --detach "$PIO_USB_COMMIT" )
fi

echo "done. libs are in $LIB"
echo "  tinyusb      : $TINYUSB_COMMIT"
echo "  Pico-PIO-USB : $PIO_USB_COMMIT"
