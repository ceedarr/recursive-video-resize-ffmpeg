#!python3.11
import ffmpeg, time, os, shutil, sys, subprocess, datetime, logging
from pathlib import Path
import ctypes
import ctypes.wintypes

class VideoResize:
    """
    インスタンス変数：
        - current_dir: カレントディレクトリ
        - config_dict: 設定を格納する辞書
        - video_pathls: 対象動画ファイルのPathリスト
        - video_info_dict: 各動画のメタデータ（解像度、ビットレート、fps、再生時間）を格納する辞書
        - resize_param_dict: 各動画のリサイズ後パラメータと「変換要否」フラグ
        - logger: ログ出力用ロガー
    メソッド：
        - normalize_paths: ファイル名・フォルダ名の正規化（不正文字の置換）を実施
        - init_logger: ログ出力の初期化
        - get_videos: 指定パスから対象動画ファイルを収集
        - get_infoDict: 各動画のメタデータを取得
        - set_parameters: リサイズ後のサイズ、ビットレート、fpsを計算し、変換要否を判定
        - resize: ffmpegによる変換／コピー実行＋変換後ファイルサイズチェック、メタデータ引き継ぎ
        - run: 全処理を実行する

    コマンドライン引数：
        - --input, -i: 入力パス（ファイルまたはディレクトリ）
        - --output, -o: 出力ディレクトリ
        - --recursive, -r: 再帰的に動画ファイルを検索するか（True／False）
        - --mode, -m: リサイズモード（"fullhd", "4k", "1920box", "3840box", "custom", "divide"）
        - --custom_param: modeが"custom"なら (width, height)、"divide"なら倍率(float)
        - --limit_direction, -l: リサイズ時に考慮する方向（"x", "y", "xy"）
        - --min_size, -s: リサイズ後の最小サイズ（幅, 高さ）
        - --fps, -f: fpsの上限
        - --bitrate, -b: ビットレートの上限（bps）
        - --nochange_copy, -nc: 変換不要の場合、ファイルをコピーするか（True) 否か（False）

    事前インストール：
        - ffmpeg-python
        - pandas
        - pathlib

    """
    def __init__(self, internal_argv=None) -> None:
        try:  # .pyとして実行された場合
            this_file = Path(__file__)
            user_argv = sys.argv[1:]
        except NameError:  # Jupyter Notebook等の場合
            this_file = Path("__file__")
            user_argv = internal_argv if internal_argv is not None else []
        current_dir = this_file.parent
        os.chdir(current_dir)
        self.current_dir = current_dir

        # 初期設定（後でコマンドライン引数で上書き）
        config_dict = {
            "input": Path("./"),           # 入力パス（ファイルまたはディレクトリ）
            "output": Path("./output"),      # 出力ディレクトリ
            "recursive": True,             # 再帰的に動画ファイルを検索するか
            "mode": "3840box",             # "fullhd", "4k", "1920box", "3840box", "custom", "divide"
            "custom_param": None,          # modeが"custom"なら (width, height)、"divide"なら倍率(float)
            "limit_direction": "xy",       # リサイズ時に考慮する方向："x", "y", "xy"
            "min_size": (1, 1),            # リサイズ後の最小サイズ（幅, 高さ）
            "fps": 60,                   # fpsの上限
            "bitrate": 4500000,            # ビットレートの上限（bps）
            "nochange_copy": False         # 変換不要の場合、ファイルをコピーするか（True）否か（False）
        }

        # コマンドライン引数による上書き（例：--input, --output, --mode, --min_size, --fps, --bitrate, --nochange_copy 等）
        def add_index(index, increment=1):
            return index + increment
        idx = 0
        while idx < len(user_argv):
            cmd = user_argv[idx]
            idx = add_index(idx)
            if cmd in ("--input", "-i"):
                path = Path(user_argv[idx])
                idx = add_index(idx)
                if path.exists():
                    config_dict["input"] = path
                else:
                    raise FileNotFoundError(f"指定されたパス '{path}' は存在しません")
            elif cmd in ("--output", "-o"):
                path = Path(user_argv[idx])
                idx = add_index(idx)
                os.makedirs(path, exist_ok=True)
                config_dict["output"] = path
            elif cmd in ("--recursive", "-r"):
                rec = user_argv[idx]
                idx = add_index(idx)
                if rec.lower() == "true":
                    config_dict["recursive"] = True
                elif rec.lower() == "false":
                    config_dict["recursive"] = False
                else:
                    raise ValueError(f"再帰処理の指定 '{rec}' は無効です")
            elif cmd in ("--mode", "-m"):
                mode = user_argv[idx]
                idx = add_index(idx)
                if mode.lower() in ("fullhd", "4k", "1920box", "3840box"):
                    config_dict["mode"] = mode.lower()
                elif mode.lower() == "custom":
                    w, h = user_argv[idx:idx+2]
                    idx = add_index(idx, 2)
                    w, h = int(w), int(h)
                    if w < 1 or h < 1:
                        raise ValueError(f"カスタム解像度 '{(w, h)}' は自然数である必要があります")
                    config_dict["mode"] = "custom"
                    config_dict["custom_param"] = (w, h)
                elif mode.lower() == "divide":
                    ratio = float(user_argv[idx])
                    idx = add_index(idx)
                    if not 0 < ratio < 1:
                        raise ValueError(f"倍率 '{ratio}' は有効な範囲 (0,1) にありません")
                    config_dict["mode"] = "divide"
                    config_dict["custom_param"] = ratio
                else:
                    raise ValueError(f"モード '{mode}' は無効です")
            elif cmd in ("--limit_direction", "-l"):
                direction = user_argv[idx]
                idx = add_index(idx)
                if direction in ("x", "y", "xy"):
                    config_dict["limit_direction"] = direction
                else:
                    raise ValueError(f"制限方向 '{direction}' は無効です")
            elif cmd in ("--min_size", "-s"):
                w_min, h_min = user_argv[idx:idx+2]
                idx = add_index(idx, 2)
                w_min, h_min = int(w_min), int(h_min)
                if w_min < 1 or h_min < 1:
                    raise ValueError(f"最小サイズ '{(w_min, h_min)}' は自然数である必要があります")
                config_dict["min_size"] = (w_min, h_min)
            elif cmd in ("--fps", "-f"):
                fps = float(user_argv[idx])
                idx = add_index(idx)
                if fps <= 0:
                    raise ValueError(f"フレームレート '{fps}' は正の数である必要があります")
                config_dict["fps"] = fps
            elif cmd in ("--bitrate", "-b"):
                bitrate = int(user_argv[idx])
                idx = add_index(idx)
                if bitrate <= 0:
                    raise ValueError(f"ビットレート '{bitrate}' は正の数である必要があります")
                config_dict["bitrate"] = bitrate
            elif cmd in ("--nochange_copy", "-nc"):
                val = user_argv[idx]
                idx = add_index(idx)
                if val.lower() in ("true", "yes", "1"):
                    config_dict["nochange_copy"] = True
                elif val.lower() in ("false", "no", "0"):
                    config_dict["nochange_copy"] = False
                else:
                    raise ValueError(f"無効な値 '{val}' が--nochange_copyに指定されました")
            else:
                raise ValueError(f"未知の引数 '{cmd}' が指定されました")
        self.config_dict = config_dict

        self.logger = None
        self.init_logger()

    def init_logger(self):
        """ログの初期化（コンソール出力＋ファイル出力）"""
        self.logger = logging.getLogger("VideoResizeLogger")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        log_filename = self.current_dir / f"log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        fh = logging.FileHandler(log_filename, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh.setFormatter(formatter)
        self.logger.addHandler(sh)
        self.logger.info("Logger initialized.")

    def normalize_filename(self, name: str) -> str:
        """
        不正な文字を置換してファイル名を正規化する。
         ・半角スペース -> '_'
         ・アポストロフィ、ダブルクォート、キャレット -> '~'
         ・コロン -> '='
         ・'*', '?', '<', '>', '|' などは適宜置換または除去
        """
        replacements = {
            " ": "_",
            "'": "~",
            '"': "~",
            "^": "~",
            ":": "=",
            "*": "_",
            "?": "",
            "<": "",
            ">": "",
            "|": "_"
        }
        for old, new in replacements.items():
            name = name.replace(old, new)
        return name

    def normalize_paths(self):
        """
        入力ディレクトリ以下のファイル名およびディレクトリ名を正規化する。
        ディレクトリ構造は保持しつつ、不正文字があれば置換してリネームする。
        """
        input_path = self.config_dict["input"]
        if input_path.is_dir():
            # 内部ディレクトリから順に（bottom-up）名前変更する
            for root, dirs, files in os.walk(input_path, topdown=False):
                # ファイル名の正規化
                for filename in files:
                    new_filename = self.normalize_filename(filename)
                    if new_filename != filename:
                        old_file = Path(root) / filename
                        new_file = Path(root) / new_filename
                        try:
                            os.rename(old_file, new_file)
                            self.logger.info(f"ファイル名変更: {old_file} -> {new_file}")
                        except Exception as e:
                            self.logger.error(f"ファイル名変更失敗: {old_file} -> {new_file}: {e}")
                # ディレクトリ名の正規化
                for dirname in dirs:
                    new_dirname = self.normalize_filename(dirname)
                    if new_dirname != dirname:
                        old_dir = Path(root) / dirname
                        new_dir = Path(root) / new_dirname
                        try:
                            os.rename(old_dir, new_dir)
                            self.logger.info(f"ディレクトリ名変更: {old_dir} -> {new_dir}")
                        except Exception as e:
                            self.logger.error(f"ディレクトリ名変更失敗: {old_dir} -> {new_dir}: {e}")
        else:
            # 入力がファイルの場合
            new_name = self.normalize_filename(input_path.name)
            if new_name != input_path.name:
                new_path = input_path.parent / new_name
                try:
                    os.rename(input_path, new_path)
                    self.logger.info(f"入力ファイル名変更: {input_path} -> {new_path}")
                    self.config_dict["input"] = new_path
                except Exception as e:
                    self.logger.error(f"入力ファイル名変更失敗: {input_path} -> {new_path}: {e}")

    def get_videos(self, extensions: list = ["mp4", "mov"]) -> None:
        """
        入力パスがディレクトリの場合、対象の動画ファイルを再帰的（または非再帰的）に取得する。
        入力がファイルの場合はそのファイルのみをリストに追加する。
        ※出力先フォルダ（config_dict["output"]）内のファイルは対象から除外する。
        """
        self.normalize_paths()  # まずファイル名・フォルダ名の正規化を実施
        config_dict = self.config_dict
        input_dir = config_dict["input"]
        recursive = config_dict["recursive"]
        output_dir = config_dict["output"]

        video_pathls = []
        if input_dir.is_file():
            # 入力がファイルの場合は、そのファイルを対象にする
            video_pathls.append(input_dir)
            # 入力がファイルの場合、親ディレクトリを入力基準にする
            config_dict["input"] = input_dir.parent
        elif input_dir.is_dir():
            if recursive:
                # 再帰的に動画ファイルを取得する場合
                # os.walk() を用いて input_dir 以下を走査。出力先フォルダ内はスキップする。
                input_dir_resolved = input_dir.resolve()
                output_dir_resolved = output_dir.resolve()
                for root, dirs, files in os.walk(input_dir_resolved):
                    current_path = Path(root)
                    # 現在のディレクトリが output_dir またはそのサブディレクトリの場合は、スキップ
                    try:
                        # relative_to() が成功すれば current_path は output_dir の下にある
                        current_path.relative_to(output_dir_resolved)
                        continue
                    except ValueError:
                        # current_path は output_dir の外にあるので処理を続行
                        pass
                    for file in files:
                        if any(file.lower().endswith("." + ext.lower()) for ext in extensions):
                            video_pathls.append(current_path / file)
            else:
                # 非再帰的に input_dir の直下のファイルを取得
                for file in input_dir.iterdir():
                    if file.is_file() and any(file.name.lower().endswith("." + ext.lower()) for ext in extensions):
                        # 出力先フォルダが input_dir 直下にあれば除外
                        if file.resolve().parent.resolve() == output_dir.resolve():
                            continue
                        video_pathls.append(file)
            if not video_pathls:
                raise ValueError(f"拡張子 {extensions} に該当するファイルが見つかりません")
        self.video_pathls = video_pathls
        self.logger.info(f"取得した動画ファイル数: {len(video_pathls)}")

    def get_infoDict(self):
        """
        各動画について、ffmpeg.probeを用いて解像度、ビットレート、fps、再生時間などのメタデータを取得する。
        """
        def get_info(video_path: Path):
            try:
                video_all_info_dict = ffmpeg.probe(str(video_path))
                streams = video_all_info_dict.get("streams", [])
                video_info = None
                for stream in streams:
                    if stream.get("codec_type") == "video":
                        video_info = stream
                        break
                if video_info is None:
                    self.logger.warning(f"ビデオストリームが検出されません: {video_path}")
                    return None
                return video_info
            except Exception as e:
                self.logger.error(f"ffmpeg.probe失敗: {video_path} : {e}")
                return None

        video_info_dict = {}
        for path in self.video_pathls:
            info = get_info(path)
            if info is not None:
                video_info_dict[path] = {
                    "size": (int(info["width"]), int(info["height"])),
                    "bit_rate": int(info.get("bit_rate", 0)),
                    "avg_frame_rate": float(eval(info["avg_frame_rate"])) if "avg_frame_rate" in info else 0.0,
                    "duration": float(info.get("duration", 0))
                }
        self.video_info_dict = video_info_dict
        self.logger.info("動画メタデータの取得完了.")

    def set_parameters(self):
        """
        各動画ごとにリサイズ後のサイズ、ビットレート、fpsを計算し、
        変換が必要かどうか（＝元と変わらない場合はスキップ／コピーするかどうか）を判定する。
        """
        config_dict = self.config_dict
        video_info_dict = self.video_info_dict

        def set_size(origin_size, mode, custom_param, min_size, limit_direction):
            preset_sizes = {
                "fullhd": (1920, 1080),
                "4k": (3840, 2160),
                "1920box": (1920, 1920),
                "3840box": (3840, 3840),
                "custom": custom_param,
                "divide": custom_param  # この場合、custom_paramは倍率(float)
            }
            if mode in ("fullhd", "4k", "1920box", "3840box", "custom"):
                target = preset_sizes[mode]
                origin_w, origin_h = origin_size
                target_w, target_h = target
                ratio_w = target_w / origin_w if origin_w > target_w else 1
                ratio_h = target_h / origin_h if origin_h > target_h else 1
                if limit_direction == "x":
                    ratio = ratio_w
                elif limit_direction == "y":
                    ratio = ratio_h
                else:  # "xy"
                    ratio = min(ratio_w, ratio_h)
            elif mode == "divide":
                ratio = custom_param
            # 計算後のサイズがmin_sizeより小さくならないよう調整
            origin_w, origin_h = origin_size
            new_w = int(origin_w * ratio)
            new_h = int(origin_h * ratio)
            min_w, min_h = min_size
            if new_w < min_w or new_h < min_h:
                ratio_w = min_w / origin_w
                ratio_h = min_h / origin_h
                if limit_direction == "x":
                    ratio = max(ratio, ratio_w)
                elif limit_direction == "y":
                    ratio = max(ratio, ratio_h)
                else:
                    ratio = max(ratio, ratio_w, ratio_h)
                new_w = int(origin_w * ratio)
                new_h = int(origin_h * ratio)
            # 偶数サイズに調整
            if new_w % 2 == 1:
                new_w += 1
            if new_h % 2 == 1:
                new_h += 1
            return (new_w, new_h)

        def set_bit_rate(origin_bitrate, config_bitrate):
            return config_bitrate if origin_bitrate > config_bitrate else origin_bitrate

        def set_fps(origin_fps, config_fps):
            return config_fps if origin_fps > config_fps else origin_fps

        resize_param_dict = {}
        for path, info in video_info_dict.items():
            orig_size = info["size"]
            orig_bitrate = info["bit_rate"]
            orig_fps = info["avg_frame_rate"]
            new_size = set_size(orig_size, config_dict["mode"], config_dict["custom_param"], config_dict["min_size"], config_dict["limit_direction"])
            new_bitrate = set_bit_rate(orig_bitrate, config_dict["bitrate"])
            new_fps = set_fps(orig_fps, config_dict["fps"])
            change_required = (new_size != orig_size) or (new_bitrate != orig_bitrate) or (new_fps != orig_fps)
            resize_param_dict[path] = {
                "size": new_size,
                "bit_rate": new_bitrate,
                "fps": new_fps,
                "change_required": change_required,
                "orig_size": orig_size,
                "orig_bit_rate": orig_bitrate,
                "orig_fps": orig_fps
            }
        self.resize_param_dict = resize_param_dict
        self.logger.info("リサイズパラメータの設定完了.")

    def copy_file_times(self, src, dst):
        """
        src から dst に対して、更新日時・アクセス日時はもちろん、
        Windows環境の場合は作成日時も含めたファイルのタイムスタンプ情報を引き継ぐ。
        """
        # 通常のファイル属性（アクセス・更新日時）のコピー
        shutil.copystat(src, dst)

        # Windowsの場合、作成日時も明示的に設定する（Unix系OSでは不要または不可）
        if os.name == 'nt':

            kernel32 = ctypes.windll.kernel32
            GENERIC_WRITE = 0x40000000
            OPEN_EXISTING = 3
            FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

            st = os.stat(src)
            # Pylanceの警告に従い、st_birthtime があればそれを使用。なければ st_ctime を使用する。
            creation_time = getattr(st, "st_birthtime", st.st_ctime)
            atime = st.st_atime  # アクセス日時
            mtime = st.st_mtime  # 更新日時

            def to_filetime(t):
                # FILETIME は 1601年1月1日からの100ナノ秒単位の値
                t_int = int((t + 11644473600) * 10000000)
                low = t_int & 0xFFFFFFFF
                high = t_int >> 32
                return ctypes.wintypes.FILETIME(low, high)

            creation_ft = to_filetime(creation_time)
            access_ft = to_filetime(atime)
            modified_ft = to_filetime(mtime)

            # ファイルハンドルの取得
            handle = kernel32.CreateFileW(
                str(dst),
                GENERIC_WRITE,
                0,
                None,
                OPEN_EXISTING,
                FILE_FLAG_BACKUP_SEMANTICS,
                None
            )
            if handle in (0, -1):
                raise ctypes.WinError()
            # 作成日時、アクセス日時、更新日時を設定
            ret = kernel32.SetFileTime(handle,
                                    ctypes.byref(creation_ft),
                                    ctypes.byref(access_ft),
                                    ctypes.byref(modified_ft))
            if ret == 0:
                kernel32.CloseHandle(handle)
                raise ctypes.WinError()
            kernel32.CloseHandle(handle)

    def resize(self):
        """
        各動画に対してリサイズ（または変換不要の場合のコピー）を実行する。
        ・出力時は、入力ディレクトリ以下の構造を保持する。
        ・変換後、出力ファイルサイズが元より大きい場合は、元ファイルをコピーする。
        ・また、変換後はshutil.copystat()を用いて作成日時・更新日時などのメタデータを引き継ぐ。
        """
        config_dict = self.config_dict
        output_dir = config_dict["output"]
        os.makedirs(output_dir, exist_ok=True)
        resize_param_dict = self.resize_param_dict

        # OSに応じたffmpegコマンドのプレフィックス設定（Windowsの場合は start /LOW /MIN を利用）
        if os.name == 'nt':
            command_prefix = ["start", "/LOW", "/MIN"]
        else:
            command_prefix = []

        total_videos = len(resize_param_dict)
        self.logger.info(f"{len(resize_param_dict)} 個の動画をリサイズします")
        resize_start_time = time.time()

        # enumerateを利用して動画ごとの処理後に進捗と終了予測時刻を表示
        num_deletedVideos = 0
        for idx, (path, params) in enumerate(resize_param_dict.items()):
            # 出力ファイルは入力ディレクトリ構造を保持する
            input_base = self.config_dict["input"].resolve()
            video_abs = path.resolve()
            output_path = output_dir / video_abs.relative_to(input_base)
            os.makedirs(output_path.parent, exist_ok=True)


            # 出力先に同名のファイルが既に存在する場合は処理をスキップする
            if output_path.exists():
                self.logger.info(f"出力ファイルが既に存在するためスキップ: {output_path}")
                num_deletedVideos += 1
                continue

            if not params["change_required"]:
                self.logger.info(f"変換不要: {path}")
                num_deletedVideos += 1
                if config_dict["nochange_copy"]:
                    try:
                        shutil.copy2(path, output_path)
                        self.logger.info(f"コピー実行（メタデータ引き継ぎ）: {path} -> {output_path}")
                    except Exception as e:
                        self.logger.error(f"コピー失敗: {path} -> {output_path}: {e}")
                else:
                    self.logger.info(f"スキップ: {path}")
            else:
                size = params["size"]
                bit_rate = params["bit_rate"]
                fps = params["fps"]

                # ffmpegコマンドの組み立て
                command = command_prefix + [
                    "ffmpeg",
                    "-y",  # 上書き確認なし
                    "-i", str(path),
                    "-b:v", f"{bit_rate/1000}k",
                    "-c:v", "h264",
                    "-c:a", "copy",
                    "-r", f"{fps}",
                    "-s", f"{size[0]}x{size[1]}",
                    str(output_path)
                ]
                self.logger.info(f"変換実行: {path} -> {output_path}")
                self.logger.debug(f"コマンド: {' '.join(command)}")
                try:
                    result = subprocess.run(" ".join(command),
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE,
                                            shell=True,
                                            encoding="utf-8")
                    if result.returncode != 0:
                        self.logger.error(f"ffmpegエラー: {path} -> {output_path}\n{result.stderr}")
                        continue
                except Exception as e:
                    self.logger.error(f"ffmpeg実行失敗: {path} -> {output_path}: {e}")
                    continue

                # 変換後のファイルサイズチェックおよびメタデータ引き継ぎ部分の変更例
                try:
                    input_size = os.path.getsize(path)
                    output_size = os.path.getsize(output_path)
                    if output_size > input_size:
                        self.logger.warning(f"変換後ファイルサイズが大きい: {path} (元: {input_size} bytes, 変換後: {output_size} bytes)")
                        shutil.copy2(path, output_path)
                        self.logger.info(f"元ファイルをコピー: {path} -> {output_path}")
                    else:
                        try:
                            # 従来の copystat() の代わりに copy_file_times() を使用
                            self.copy_file_times(path, output_path)
                            self.logger.info(f"メタデータ引き継ぎ: {path} -> {output_path}")
                        except Exception as e:
                            self.logger.error(f"メタデータ引き継ぎ失敗: {path} -> {output_path}: {e}")
                except Exception as e:
                    self.logger.error(f"ファイルサイズチェック失敗: {path} -> {output_path}: {e}")

            # 動画1本ごとの処理が完了した時点で、終了予測時刻を計算して表示
            processed_count = idx + 1
            # 変換不要の場合はカウントしない
            processed_count_for_calculation = processed_count - num_deletedVideos
            total_videos_for_calculation = total_videos - num_deletedVideos
            elapsed_time = time.time() - resize_start_time
            avg_time_per_video = elapsed_time / processed_count_for_calculation
            estimated_total_time = avg_time_per_video * total_videos_for_calculation
            estimated_finish_time = resize_start_time + estimated_total_time
            finish_dt_str = datetime.datetime.fromtimestamp(estimated_finish_time).strftime('%Y-%m-%d %H:%M:%S')
            self.logger.info(f"動画 {processed_count}/{total_videos} 処理完了。終了予測時刻: {finish_dt_str}")


    def run(self):
        start_time = time.time()
        self.logger.info("リサイズ処理開始")
        self.get_videos()
        self.get_infoDict()
        self.set_parameters()
        self.resize()
        elapsed = datetime.timedelta(seconds=int(time.time() - start_time))
        self.logger.info(f"リサイズ処理完了。所要時間: {elapsed}")

if __name__ == "__main__":
    vr = VideoResize()
    vr.run()
