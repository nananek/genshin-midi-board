# AGENTS.md

このリポジトリで作業する人（エージェントを含む）向けのルールです。作業前に必ず読んでください。

## 1. プロジェクトの前提

- RP2040 + CH345T の 4 層基板、RP2040 ファームウェア、A4 紙ケースの設計検討リポジトリです。
- 設計値の正本は `hardware/rp2040_midi_bridge/design.yaml` です。回路図、PCB、ピン表、BOM、配置は生成物なので、手で直す前に生成元を直します。
- 生成と検証は次で行います。

```sh
make check        # 設計制約 + PCB 監査 + 単体テスト
make erc          # 回路図 ERC
make drc          # PCB DRC
make tables       # pinmap.csv / bom.csv / placement.csv
make netlist      # netlist.yaml
make floorplan    # floorplan.svg
make paper-case   # 紙ケースの PDF / SVG
```

- 製造データを作る前に、`make check`、ERC 0、DRC 0 violations / 0 unconnected を通します。
- 生成物をコミットする場合は、必ず生成コマンドを実行したあとの差分にします。生成スクリプトと手作業の出力を混在させません。

## 2. 記述ルール

- 個人の作業環境に固有の製品名、機材名、他リポジトリ名、ローカルパスを書かないでください。必要なら「USB MIDI キーボード」「以前の試作」「別のリポジトリ」のような一般名詞に置き換えます。
- 過去に作った別構成の基板やチップの比較・経緯は書きません。現在の設計に必要な情報だけを残します。
- 日本語の文書は常体で、結論から書きます。同じ内容を README と docs に重複させるときは、片方を正本にしてもう片方はリンクにします。
- 数値は `design.yaml` と `docs/design.md` を正とし、README や図に転記した数値がずれたら設計側に合わせます。

## 3. 製造データ（ガーバー）の配布

ガーバー、ドリル、BOM、CPL は設計ソースではありません。次のルールで扱います。

### 3.1 リポジトリに入れない

- 生成したガーバー、ドリル、BOM、CPL、ZIP はコミットしません。`dist/`、`gerbers/`、`fab/` などの作業ディレクトリに置き、`.gitignore` で除外します。
- 配布物は Git のリリース（タグ + 添付ファイル）で渡します。リポジトリの履歴にバイナリを積みません。

### 3.2 配布してよい条件

次のすべてを満たしたリビジョンだけを配布します。

1. クリーンな作業ツリーで、配布対象のコミットにタグを打っている。
2. `make check`、ERC 0、DRC 0 violations / 0 unconnected が通っている。
3. JLCPCB の DFM プレビューで via-in-pad、0.15 mm ドリル、blind/buried via の指摘がない。
4. ドリルファイルに 0.15 mm が 1 本もない。
5. BOM と CPL の部品番号、位置、回転を実装プレビューで確認している。
6. 実機で未検証の場合は、配布物とリリースノートに「未検証の試作」と明記している。

条件を満たさない途中版を「製造用」として配布しません。

### 3.3 配布物の構成

1 つの ZIP に次を入れます。

```text
rp2040_midi_bridge-v<version>-gerber.zip
  gerbers/                 Gerber X2（全層）
  gerbers/*.drl            Excellon ドリル（PTH / NPTH）
  bom.csv                  JLCPCB 形式の BOM
  cpl.csv                  JLCPCB 形式の CPL
  manifest.sha256          上記ファイルの SHA-256
  README.txt               リビジョン、コミット、KiCad 版、層構成、既知の問題
  LICENSE                  MIT
```

- ファイル名は `rp2040_midi_bridge-v<version>-gerber.zip` に固定します。
- `README.txt` には、タグ名、コミットハッシュ、KiCad のバージョン、基板仕様（62.0 × 35.0 × 1.6 mm、4 層）、既知の問題を書きます。
- `manifest.sha256` は ZIP を作る直前に生成し、ZIP の中身と一致させます。
- 配布物にローカルパス、ユーザー名、ホスト名、VM 固有のパスを入れません。

### 3.4 ライセンス

- リポジトリ全体は MIT です（`LICENSE`）。
- `hardware/rp2040_midi_bridge/lib/` の KiCad シンボルは公式 KiCad ライブラリ由来で、CC-BY-SA 4.0（設計への利用例外あり）です。配布物に含める場合は `LICENSE` と合わせてこの旨を `README.txt` に書きます。
- ファームウェアが取得する外部依存（pico-sdk、TinyUSB、Pico-PIO-USB）はリポジトリに同梱しません。ビルド手順だけを示します。

### 3.5 配布しないもの

- 個人情報、認証情報、API キー、署名鍵。
- 実機のシリアル番号や検査記録など、配布対象の設計と関係ない情報。
- 他者の著作物を出所不明のまま同梱したもの。フットプリントやシンボルを追加するときは、出所とライセンスを確認します。

## 4. 変更の提出

- コミットは署名付きで行います。`--no-gpg-sign` は使いません。
- 変更は小さな単位に分け、設計値の変更と生成物の更新を同じコミットにまとめます。
- プルリクエストの本文には、変更内容、検証コマンドと結果、未確認事項を書きます。
