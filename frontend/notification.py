import subprocess

def output(text: str):
    preview = text[:60].replace("\n", " ").strip()
    subprocess.run(["wl-copy"], input=text, text=True)
    if preview:
        subprocess.run(["notify-send", "转录结果", preview])
