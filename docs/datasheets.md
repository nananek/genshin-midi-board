# 部品データシートと向きの確認

IC と向きのある部品のデータシート、LCSC 型番、実装時の確認方法をまとめる。CPL の回転値は `make fab` が出力する `dist/...-cpl.csv` を正とし、最終確認は JLCPCB の実装プレビューで行う。

## IC

| Ref | 型番 | メーカー | パッケージ | LCSC | データシート | pin1 / CPL |
| --- | --- | --- | --- | --- | --- | --- |
| U1 | RP2040 | Raspberry Pi | QFN-56 | [C2040](https://www.lcsc.com/product-detail/C2040.html) | [RP2040 datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf) | pin1 ドット。CPL 270° |
| U2 | W25Q128JVSIQ | Winbond | SOIC-8 208-mil | [C97521](https://www.lcsc.com/product-detail/C97521.html) | [W25Q128JV datasheet](https://www.winbond.com/resource-files/w25q128jv%20revf%2003272018%20plus.pdf) | pin1 ドット。CPL 270° |
| U3 | CH345T | WCH | SSOP-20 | [C5246448](https://www.lcsc.com/product-detail/C5246448.html) | [CH345 product page](https://www.wch-ic.com/products/CH345.html) | pin1 ドット。CPL 270° |
| U4 | AP2112K-3.3TRG1 | Diodes | SOT-23-5 | [C51118](https://www.lcsc.com/product-detail/C51118.html) | [AP2112 datasheet](https://www.diodes.com/assets/Datasheets/AP2112.pdf) | pin1。CPL 270° |
| U5 | TPS2553DBVR | Texas Instruments | SOT-23-6 | [C55266](https://www.lcsc.com/product-detail/C55266.html) | [TPS2553 datasheet](https://www.ti.com/lit/ds/symlink/tps2553.pdf) | pin1 = IN。CPL 180° |
| U6/U7 | USBLC6-2SC6 | STMicroelectronics | SOT-23-6 | [C7519](https://www.lcsc.com/product-detail/C7519.html) | [USBLC6-2 datasheet](https://www.st.com/resource/en/datasheet/usblc6-2.pdf) | pin1 = I/O1。CPL 270° |
| U8 | USBLC6-2SC6 | STMicroelectronics | SOT-23-6 | [C7519](https://www.lcsc.com/product-detail/C7519.html) | [USBLC6-2 datasheet](https://www.st.com/resource/en/datasheet/usblc6-2.pdf) | pin1 = I/O1。基板 90°、CPL 0° |

## IC フットプリント照合

`make ic-footprints` で routed board から [ic_footprints.md](ic_footprints.md) を生成する。データシートの package と照合した結果は次のとおり。

| Ref | KiCad footprint | データシート package | 判定 |
| --- | --- | --- | --- |
| U1 | `Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm` | QFN-56 7x7 mm, 0.4 mm, EP 3.2x3.2 mm | 一致 |
| U2 | `Package_SO:SOIC-8_5.3x5.3mm_P1.27mm` | SOIC-8 208-mil (5.28x5.18 mm), 1.27 mm | 一致 |
| U3 | `rp2040_midi_bridge:SSOP-20_5.3x7.2mm_P0.65mm` | SSOP-20 5.3x7.2 mm body, 7.0 mm pad row, 0.65 mm | 一致 |
| U4 | `Package_TO_SOT_SMD:SOT-23-5` | SOT-23-5 | 一致 |
| U5 | `Package_TO_SOT_SMD:SOT-23-6` | SOT-23-6 | 一致 |
| U6/U7 | `Package_TO_SOT_SMD:SOT-23-6` | SOT-23-6 | 一致 |
| U8 | `Package_TO_SOT_SMD:SOT-23-6` | SOT-23-6 | 一致 |

U2 は W25Q128JVSIQ の 208-mil パッケージに `SOIC-8_5.3x5.3mm_P1.27mm` を使っている。すべての IC がデータシートの package と一致している。

## 向きのある参考部品

| Ref | 部品 | リンク | 向きの確認 |
| --- | --- | --- | --- |
| D1/D2 | BAT54WS | [BAT54W datasheet](https://www.diodes.com/assets/Datasheets/ds11005.pdf)、[LCSC C22629](https://www.lcsc.com/product-detail/C22629.html) | カソード帯が `+5V` 側。D1 は 90°、D2 は 0° |
| X1/X2 | 12 MHz 3225 4-pin | [LCSC C50430](https://www.lcsc.com/product-detail/C50430.html) | pin1 は左下。pad1 が `XIN` / `XI`、pad2/pad4 が GND |
| J1/J3 | HRO TYPE-C-31-M-12 | [HRO drawing](http://www.krhro.com/uploads/soft/180320/1-1P320120243.pdf)、[LCSC C165948](https://www.lcsc.com/product-detail/C165948.html) | 開口とキーの向き。CPL 180°、位置は 1.571 mm 補正 |
| J2 | Neltron 5075AR-04-WH | [Neltron drawing](https://akizukidenshi.com/goodsaffix/5075AR-04-WH-F1.pdf)、[Akizuki 100160](https://akizukidenshi.com/catalog/g/g100160/) | THT。シェル穴は開口側 2.7 mm。開口を基板端に合わせる |
| SW1〜SW4 | NKK 115643 | [Akizuki 115643](https://akizukidenshi.com/catalog/g/g115643/) | THT。レバーの向きをケース開口に合わせる |
| SW5 | DTS-63-N-V-BLK | [Akizuki 103647](https://akizukidenshi.com/catalog/g/g103647/) | THT。押し子の向きを確認する |
| SW6/SW7 | C&K KMR2 | [LCSC C2689528](https://www.lcsc.com/product-detail/C2689528.html) | SMT。pad1/pad2 と押し子の向き。CPL 0° |
| C27 | 100 uF 1210 | [LCSC C96123](https://www.lcsc.com/product-detail/C96123.html) | 設計はセラミックで無極性。電解質に変える場合のみ極性を確認する |

## 確認方法

1. **JLCPCB の実装プレビュー**
   - 66 SMT 点すべてで pin1 マーク、カソード帯、コネクタ開口、スイッチの押し子を確認する。
   - CPL の Rotation は JLCPCB の部品ライブラリ基準で、KiCad の回転とは別物として扱う。
2. **KiCad の 3D / フットプリント**
   - pad1 の位置とネット名を、データシートの pin1 と突き合わせる。
   - IC は pin1 ドット、ダイオードはカソード帯、水晶は pin1 の面取り/ドットを見る。
3. **THT 部品**
   - J2 と SW1〜SW5 は 1:1 プリントと現物で、シェル穴、開口、レバー、押し子の向きを確認する。
4. **テスター**
   - D1/D2 はダイオードモードで、`VBUS_PC` / `VBUS_IPAD` から `+5V` 方向が約 0.2〜0.35 V、逆が OL であることを確認する。
   - X1/X2 は pad2/pad4 の GND 導通と、pad1/pad3 が `XIN` / `XOUT` と各ロードコンデンサへ導通することを確認する。水晶自体の良否は発振で確認する。
5. **実装後**
   - X1 は RP2040 の USB 認識、X2 は CH345T の USB-MIDI 認識で発振を確認する。
   - U5 は pin1 = IN が `+5V` パッド側に来ているか、JLCPCB のプレビューで確認する。

## CPL の回転値

`make fab` の `CPL_ROTATION_OFFSETS` で補正する。現在の値は次のとおり。

| Ref | 基板回転 | CPL | 補正 |
| --- | ---: | ---: | ---: |
| U1 | 270° | 270° | 0° |
| U2 | 0° | 270° | 270° |
| U3 | 0° | 270° | 270° |
| U4 | 0° | 270° | 270° |
| U5 | 0° | 180° | 180° |
| U6/U7 | 0° | 270° | 270° |
| U8 | 90° | 0° | 270° |
| J1/J3 | 180° | 180° | 0° |
| D1 | 90° | 90° | 0° |
| D2 | 0° | 0° | 0° |
| LED1 | 0° | 0° | 0° |
| X1/X2 | 0° | 0° | 0° |
| SW6/SW7 | 0° | 0° | 0° |
| C27 | 0° | 0° | 0° |

U5 は TPS2553 の pin1 = IN に合わせて、CPL を 0° から 180° に補正している。
