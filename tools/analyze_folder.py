#!/usr/bin/env python3
import os
from pathlib import Path
from datetime import datetime

ROOT = Path("/Users/venky/AI-QnA-App2")
OUT_DIR = ROOT/"_reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def build_tree(path, prefix="", depth=0, max_depth=4):
    if depth>max_depth: return []
    lines=[]
    entries=sorted([e for e in path.iterdir() if not e.name.startswith(".")])
    for i,e in enumerate(entries):
        conn="└── " if i==len(entries)-1 else "├── "
        lines.append(prefix+conn+e.name)
        if e.is_dir():
            ext="    " if i==len(entries)-1 else "│   "
            lines+=build_tree(e,prefix+ext,depth+1,max_depth)
    return lines

def main():
    tree_txt="\n".join([ROOT.name]+build_tree(ROOT))
    with (OUT_DIR/"tree.txt").open("w") as f:f.write(tree_txt)

    summary=f"""# Folder Report
- Path: {ROOT}
- Generated: {datetime.utcnow().isoformat()}Z
- Tree (depth 4):
"""
    with (OUT_DIR / "folder_report.md").open("w") as f:
        f.write(summary)

    print("Reports written to", OUT_DIR)

if __name__ == "__main__":
    main()