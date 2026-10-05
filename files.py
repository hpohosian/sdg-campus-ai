import csv, shutil, pathlib

DATAROOT = pathlib.Path(r"D:\Moodle\MoodleWindowsInstaller-latest-500\server\moodledata")   # проверь по config.php
OUT = pathlib.Path("course_files")

with open(r"C:\Users\User\files.csv.csv", encoding="utf-8-sig", newline="") as f:
    for row in csv.DictReader(f):
        h = row["contenthash"]
        src = DATAROOT / "filedir" / h[:2] / h[2:4] / h
        dst = OUT / f"course_{row['courseid']}" / row["filename"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            dst = dst.with_name(f"{row['id']}_{dst.name}")
        if src.exists():
            shutil.copy2(src, dst)
        else:
            print("нет файла:", src)