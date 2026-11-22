# firmware (RP2040)

RP2040 版のファームウェアです。機能とピンの設計は
[docs/firmware.md](../docs/firmware.md)、ピンの正本は
[include/board_pins.h](include/board_pins.h) を参照してください。

```
[MIDI キーボード] --USB--> PIO-USB host (rhport 1) --+
                                                      +--> native USB = NKRO HID (rhport 0)
                                                      +--> UART1 31250 --> CH345 --> USB-MIDI
```

- デバッグログ: UART0 GP0 (TX) / GP1 (RX)、115200 8N1
- CH345: UART1 GP4 (TX) / GP5 (RX)、31250 8N1
- スイッチ: GP28 ミュート / GP29 楽器 / GP27 サステイン / GP14 MIDI リセット
- GP26 は未使用
- ステータス LED: GP25 (アクティブ HIGH)

## ホスト側ユニットテスト (ARM ツールチェーン不要)

純粋ロジック (`note_mapper` / `midi_parse` / `nkro_report`) をホスト `cc` で検証します。

```sh
cd tests
make          # 全テストをビルドして実行
make clean
```

## ARM ビルド

pico-sdk 2.x と、MIDI ホスト対応の upstream TinyUSB / Pico-PIO-USB が必要です。
依存は `scripts/fetch_deps.sh` が `lib/` 以下へ固定バージョンで取得します。

```sh
cd firmware
./scripts/fetch_deps.sh

export PICO_SDK_PATH=/path/to/pico-sdk
cmake -B build -DPICO_BOARD=pico
cmake --build build -j
```

成果物は `build/midi_nkro_ch345.uf2` です。

`PICO_BOARD=pico` は RP2040 / 2 MB flash を前提にします。基板の flash は
W25Q128 (16 MB) ですが、ファームウェアは 2 MB に収まるため既定のままで動きます。
16 MB を認識させたい場合だけカスタムボード定義で `PICO_FLASH_SIZE_BYTES` を
上書きしてください。

## サステインの送信チャンネル

SW3 は押下で CC64=127、解放で CC64=0 を送ります。チャンネルは
`config.h` の `SUSTAIN_SWITCH_MIDI_CHANNEL` (0-indexed、既定 0 = ch1) で
変更できます。MIDI キーボードの送信チャンネルに合わせてください。
SW6 は全 16 チャンネルへ CC123 / CC121 を送ります。
