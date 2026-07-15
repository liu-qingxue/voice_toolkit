import sys
import argparse
from pathlib import Path
from pydub import AudioSegment
import time

ROOT = Path(__file__).resolve().parent.parent   # 入口处必须要有!!!
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from config import Config
from core.create_transcriber import create_transcriber
import log

CFG = Config(mode= "batch")

def convert_to_wav(input_path: Path, output_path: Path):
    """将音频文件转换为 16kHz 单声道 int16 的 WAV，适合语音识别
    - path要是一个文件的路径
    """
    audio = AudioSegment.from_file(str(input_path))
    audio = audio.set_frame_rate(CFG.sample_rate).set_channels(CFG.channels).set_sample_width(2)
    audio.export(str(output_path), format="wav")

def output(text: str, path: Path):
    """path要是一个文件的路径"""
    try:
        with open(path,"w",encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        raise RuntimeError(f"写入翻译文件时错误: {e}") from e
    

def main():
    parser = argparse.ArgumentParser(description="批量转录工具")
    parser.add_argument("--input","-i",required=True,help="输入音频的目录")
    parser.add_argument("--output","-o",help="转录结果输出路径")

    args = parser.parse_args()
    audio = Path(Path(args.input).expanduser())
    if not audio.exists():
        raise FileNotFoundError(f"音频目录{audio}不存在!")
    if not args.output:
        print(f"未输入参数:[输出路径]\n将使用当前路径:[{Path.cwd}]作为输出路径")
        out = Path.cwd()
    else:
        if not Path(args.output).exists():
            print(f"输出目录[{args.output}]不存在!\n使用当前目录:[{Path.cwd}]作为输出目录!")
            is_mkdir = input(f"你想要创建[{{args.output}}]这个路径来作为输出目录吗? y|n (默认为y): ")
            if is_mkdir.lower() in ("y","yes",""):
                is_mkdir = True 
            elif is_mkdir.lower() in ("n","no"):
                print(f"输入的啥?给你放到当前目录 {Path.cwd()} 了")
                is_mkdir=False
            else:is_mkdir=False
            if is_mkdir:
                Path(args.output).mkdir(parents=True,exist_ok=True)
                out = Path(args.output)
            else:out = Path.cwd()
        else:
            out = Path(args.output)
    out = Path(out.expanduser())

    print("开始批量转录\n====> 找寻音频文件...\n")
    all_audio = {}
    AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma"}
    for f in audio.iterdir():
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
            all_audio[f.name]=f.suffix.lower()
    wav=[]
    nwav=[]
    for k,v in all_audio.items():
        if v==".wav": 
            print(f"找到了音频: {k}")
            wav.append(audio/k) 
        else:
            print(f"需要转化格式的音频文件: {k}")
            nwav.append(audio/k)


    nw_dir = Path(Path("~/.tmp_convert_to_wav/").expanduser())
    print(f"\n====> 转换音频为wav...\n转换后的音频临时放到:{nw_dir}\n")
    nw_dir.mkdir(parents=True,exist_ok=True)
    converted=[]
    t_1 = time.perf_counter()
    for nw in nwav:
        try:
            converted_p = nw_dir / (nw.stem + ".wav")
            convert_to_wav(nw,converted_p)
            converted.append(converted_p)
            wav.append(converted_p)
        except Exception as e:
            for cd in converted:
                cd.unlink(missing_ok=True)
            raise RuntimeError(f"转化非wav格式的音频的时候发生错误: {e}\n本次脚本产生文件已全部回滚删除!")
    t_2 = time.perf_counter()
    converted_time = t_2-t_1
    if not len(nwav)==len(converted):
        print(f">>>>>未知的格式转化错误?请自行检查!!!")
    else:
        print(f"\n====> 格式转换成功!!\n[格式转换用时]: {converted_time}\n")

    transcriber = create_transcriber(mode="batch")
    t_3 = time.perf_counter()
    transcriber.load()
    t_4 = time.perf_counter()
    load_time = t_4-t_3
    print(f"\n====> 模型加载成功\n[模型加载用时]: {load_time}\n")
    print("\n====> 开始转录\n")
    audio_number = len(wav)
    for la in wav:
        try:
            text = transcriber.transcribe(la)
            output_file = out/(la.stem + ".txt")
            output(text=text,path=output_file)
            print(f"""[{str(la)}]成功转录 -> {output_file}: 
                \t\t行数: {len(text.splitlines())}
                \t\t字数: {len(text.replace('\n', ''))}
                \t\t头内容:{text[:9]}""")
        except Exception as e:
            print(f"[警告!!!!] {la} 转录失败或写入错误: {e},可能存在的半成品需要自行清理")
            continue
    for uf in converted:
        try:
            uf.unlink()
        except Exception as e:
            print(f"清理临时文件 {uf} 时发生错误: {e}")
            continue
    t_5 = time.perf_counter()
    transcribe_time = t_5-t_4
    print(f"""\n====> 转录完成!
          共计转录: {audio_number} 个音频
          所有转录结果在: {out} 
          格式转换用时: {converted_time} s
          模型加载用时: {load_time} s
          转录用时: {transcribe_time} s
          """)
    

if __name__ == "__main__":
    main()