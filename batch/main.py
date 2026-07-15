# ../venv/bin/python
import sys
import argparse
from pathlib import Path
from pydub import AudioSegment
import log

ROOT = Path(__file__).resolve().parent.parent   # 入口处必须要有!!!
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from config import Config
from core.create_transcriber import create_transcriber

CFG = Config(mode= "batch")

def convert_to_wav(input_path: Path, output_path: Path):
    """将音频文件转换为 16kHz 单声道 int16 的 WAV，适合语音识别"""
    audio = AudioSegment.from_file(str(input_path))
    audio = audio.set_frame_rate(CFG.sample_rate).set_channels(CFG.channels).set_sample_width(2)
    audio.export(str(output_path), format="wav")

def output(text: str, path: Path, mode: bool=False ""):
    try:
        with open(path,"w",encoding="utf-8") as f:
            f.write(text)
    except EOFError as e:
        raise(f"写入错误: {e}")
    if mode:
        print(text)
    

def main():
    parser = argparse.ArgumentParser(description="批量转录工具")
    parser.add_argument("--input","-i",required=True,help="输入音频的目录")
    parser.add_argument("--output","-o",help="转录结果输出路径")
    parser.add_argument("--print","-p",action="store_true",help="是否打印到终端")

    args = parser.parse_args()
    audio = Path(args.input)
    if not audio.exists():
        raise(f"音频目录{audio}不存在!")
    if not args.output:
        print(f"未输入参数:[输出路径]\n将使用当前路径:[{Path.cwd}]作为输出路径")
        out = Path.cwd()
    else:
        if not Path(args.output).exists():
            print(f"输出目录[{out}]不存在!\n使用当前目录:[{Path.cwd}]作为输出目录!")
            out = Path.cwd()
        else:
            out = Path(args.output)


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


    nw_dir = Path("~/tmp_convert_to_wav/")
    print(f"\n====> 转换音频为wav...\n转换后的音频临时放到:{nw_dir}\n")
    nw_dir.mkdir(parents=True,exist_ok=True)
    converted=[]
    for nw in nwav:
        try:
            convert_to_wav(nw,nw_dir)
            converted.append(nw_dir/nw.name)
        except Exception as e:
            for cd in converted:
                cd.unlink(missing_ok=True)
            raise(f"转化非wav格式的音频的时候发生错误: {e}\n本次脚本产生文件已全部回滚删除!")
        wav.append(nw_dir/nw.name)
    if not len(nwav)==len(converted):
        print(f">>>>>未知的格式转化错误?请自行检查!!!")
    else:
        print("\n====> 格式转换成功!!\n")
    transcriber = create_transcriber(mode="batch")
    transcriber.load()
    print("\n====> 开始转录\n")
    for la in wav:
        del text
        text = transcriber.transcribe(la)
        output(text=text,path=out,mode=args.print)
        print(f"[{la.name}]成功转录并写入 {out/la.name}: \n\t\\t头内容:{text[:9]}\n\t\t行数: {len(text)}\n\t\t")
    

if __name__=="__main__":
    main()