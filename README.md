# recursive-video-resize-ffmpeg
FFmpegを用いて、再帰的に動画ファイルをリサイズするPythonプログラムです。リサイズの設定を自由に指定できます。\
実行確認済みの環境：
- Windows 11 (多分他OSでも動くが未確認)
- Python 3.11.9
- コマンドプロンプト

## 目次

* [環境構築](#環境構築)
* [使い方](#使い方)
* [オプション](#オプション)
* [プログラム処理フロー](#プログラム処理フロー)
* [補足](#補足)
* [免責事項](#免責事項)

## 環境構築
### 1. FFmpegのインストール
[公式サイト](https://ffmpeg.org/download.html)からダウンロードしてインストールしてください。\
インストール後、下記コマンドが実行できることを確認してください。
```
ffmpeg -version
```

### 2. Pythonライブラリのインストール
コマンドプロンプトで下記のコマンドを実行してvenv環境を作成してください。
```
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

Python環境がない場合、[公式サイト](https://www.python.org/downloads/)からダウンロードしてインストールしてください。


## 使い方
【`./videos`内の動画をリサイズし`./output`へ出力する場合】\
コマンドライン (cmdで実行確認済) で下記のように実行します。相対パスを用いる場合、カレントディレクトリはvideo_resize.pyの親フォルダになります。
```
python video_resize.py --input "./videos" --output "./output" --recursive true --mode custom 2560 1440 --limit_direction xy --min_size 1 1 --fps 60 --bpp 0.036 --nochange_copy true
```

【`C:\videos\video.mp4`をリサイズし`C:\resizedVideos`へ出力する場合】\
なお、オプションは短縮表記可能です。また、オプションを省略した場合、次節の表に示すデフォルト値で実行されます。
```
python video_resize.py -i "C:\videos\video.mp4" -o "C:\resizedVideos" -m fullhd -f 60 -b 0.036
```

## オプション
| オプション       | 短縮表記 | 説明                                                                   | 例     |デフォルト |
|------------------|-----|---------------------------------------------------------------------------|-----------|---------|
| --input           | -i  | 入力ディレクトリ (ファイルまたはフォルダ) (絶対パス or video_resize.pyへの相対パス)|"./videos", "C:\video.mp4" | "./"    |
| --output          | -o  | 出力先フォルダ (相対/絶対パス両対応)                         | "./output", "C:\output" |"./output"|
| --recursive       | -r  | 動画取得のために入力ディレクトリを再帰的に検索するか ("true" または "false")  | true       | true    |
| --mode (詳細↓)    | -m  | リサイズモード ("fullhd", "4k", "1920box", "3840box", "custom", "divide")  | 3840box   | 3840box |
| fullhd, 4K        |     | fullhd: 1920 * 1080, 4k: 3840 * 2160                                      |           |         |
| 1920box, 3840box  |     | 1920box: 1920 * 1920, 3840box: 3840 * 3840                                |           |         |
| custom            |     | 横と縦のピクセルサイズを数値で指定する `custom 横ピクセル 縦ピクセル`          | 2560 1440 | (なし)  |
| divide            |     | 横と縦のピクセルサイズの縮小倍率を数値で指定する `divide 倍率(0～1)`          | 0.5        | (なし)  |
| --limit_direction | -l  | リサイズ時にピクセルサイズを制限する方向 ("x", "y", "xy")                   | y          | xy      |
| --min_size        | -s  | リサイズ後の最小サイズ (幅, 高さ)                                          | 750 1000   | 1 1     |
| --fps             | -f  | fpsの上限                                                                | 30         | 60      |
| --bpp             | -b  | １ピクセル当たりのビット数 (bits per pixel) の上限                         | 0.06       | 0.036   |
| --nochange_copy   | -nc | 変換不要の場合、出力ディレクトリにファイルをコピーするか ("true", "false")   |  true      | true    |

## プログラム処理フロー

### 1. ファイル名の正規化
> [!WARNING]
>プログラム開始時、リサイズ処理でのファイル名エラー回避のため、ディレクトリ名の正規化を行います。\
>この処理により元のファイル名が完全に変更されるので、ファイル名を維持したい場合は事前に対策を講じてください。\
>または、`video_resize.py`の`VideoResize.get_videos()`メソッド冒頭の`self.normalize_paths()`をコメントアウトして正規化を無効化してください。

### 2. 各種パラメータの計算
入力されたオプションに従い、リサイズの解像度、ビットレート、fpsを計算します。\
計算の結果、リサイズ前後で全てのパラメータが同一となった場合、次のフローにおいてリサイズ処理を行わない仕様としています。このとき、`--nochange_copy`オプションが`true`であれば、このようなファイルは出力先フォルダへコピーされます。

#### 解像度
- `--mode`で指定されたサイズに収まる最大のサイズが計算されます。\
例えば、3840 * 1500の横長の動画を`--limit_direction xy`、`--mode fullhd`でリサイズする場合、リサイズ後の解像度は1920 * 750となります。`--limit_direction y`とした場合は、2764 * 1080のようになります。
- `--mode divide`の場合、指定された倍率でリサイズされます。

#### フレームレート
- `--fps`で指定されたfpsを上限として、リサイズ後のfpsが計算されます。

#### ビットレート
- `--bpp`で指定されたbppを基に、ビットレートが計算されます。計算式は下記です。
```
bitrate = bpp * width * height * fps
例: 0.036 (bpp) * 1920 (width) * 1080 (height) * 60 (fps) = 4,478,976 bps ~ 4.5 Mbps
```
こちらも同様、元ファイルより大きくならないように (大きくなれば元ファイルで上書きするよう) 設計しています。

### 3. リサイズの実行
- `subprocess`ライブラリでFFmpegを実行します。Windowsの場合、下記コマンドが実行されます。
```
start /LOW /MIN ffmpeg -i "動画ファイル" -b:v "ビットレート" -c:v h264 -c:a copy -r fps -s 横ピクセルx縦ピクセル "出力先"
```
`start /LOW /MIN ffmpeg`: 新規で最小化ウィンドウを開き、低優先度でFFmpegを実行する\
`-c:v h264`: ビデオコーデックをH.264に指定\
`-c:a copy`: オーディオコーデックをコピー（変換せず）に指定

Windowsではない場合、`start /LOW /MIN`は省かれます。

- また、Windowsで実行する場合に限り、動画ファイルのタイムスタンプをリサイズ後のファイルに引き継ぎます。

### 4. リサイズ後ファイル (or コピーファイル) の保存
下記のように格納されている動画ファイル (mp4, mov) を`--input "./"`, `--output "./output"`で再帰的にリサイズする場合、
```
parent_dir
├── video_resize.py
├── video1.mp4
├── video2.mov
└── dir1
    ├── video3.mp4
    ├── video4.mov
    └── dir2
        ├── video5.mp4
        └── video6.mov
```

ディレクトリ構造を保持しつつ出力先フォルダへ保存されます。
```
parent_dir
├── video_resize.py
├── (省略)
└── output
    ├── video1.mp4
    ├── video2.mov
    └── dir1
        ├── video3.mp4
        ├── video4.mov
        └── dir2
            ├── video5.mp4
            └── video6.mov
```

> [!NOTE]
>リサイズ処理後、元ファイルよりもかえって動画容量が大きくなることがあります。\
>このような動画ファイルはリサイズ後、元動画によって上書きされます。

### 4. ログの出力
プログラムと同じディレクトリ内にログファイルが生成されます。実行状況がコンソールに出力され、ログファイルにも記録されます。
ファイル名は"log_YYYYmmdd_HHMMSS.txt"の形式で生成されます。例えば、"log_20250216_200556.txt"のようになります。

## 補足
### 1. オプション`--limit_direction`の使いどころ
このオプションは、リサイズ時にピクセルサイズを制限する方向を指定するためのものです。\
デフォルトでは`xy`ですが、必要に応じて`x`または`y`に変更してください。\
`x`や`y`の使いどころとしては、「横にスライドする壁紙として使うために、スマホの縦ピクセルのみに合わせる」などです。


### 2. オプション`--min_size`の使いどころ
このオプションは、リサイズ後の最小サイズを指定するためのものです。\
デフォルトでは`1 1`ですが、必要に応じて変更してください。\
使用する端末や画像ビューワによっては、ズーム機能を持たず、画像が小さく表示されてしまうことがあります。\
そのような場合、端末の画面の解像度が例えば 750 × 1000 ピクセルであれば、 min_sizeを`750 1000`と設定することで、端末に合った (小さすぎない) サイズへリサイズできます。

## 免責事項
本ソフトウェアはMITライセンスに基づき「現状有姿（AS IS）」で提供されています。\
つまり、明示的・黙示的な保証は一切行われておらず、本ソフトウェアの利用に関連して発生するいかなる損害に対しても、著作者は責任を負いません。\
詳細はLICENSEファイルをご参照ください。
