#!/usr/bin/env python3
import argparse, json, os, datetime
from config import DOWNLOAD_BATCH_PATH

def load_batch(path):
    if not os.path.exists(path):
        return {"version":1,"generated_by":"download_tasks.py",
                "generated_at":datetime.datetime.utcnow().isoformat()+"Z",
                "tasks":[]}
    with open(path,"r") as f:
        return json.load(f)

def save_batch(path, data):
    data["generated_by"]="download_tasks.py"
    data["generated_at"]=datetime.datetime.utcnow().isoformat()+"Z"
    with open(path,"w") as f:
        json.dump(data,f,indent=2)

def add_track(args):
    path = args.batch or DOWNLOAD_BATCH_PATH
    data = load_batch(path)
    task = {
        "task_id": datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S"),
        "source": args.source,
        "type": "track",
        "spotify_id": args.spotify_id,
        "artist": args.artist,
        "album": args.album,
        "year": args.year,
        "title": args.title,
        "priority": args.priority,
        "status": "pending"
    }
    data["tasks"].append(task)
    save_batch(path,data)
    print("Added track:", task["title"])

def info(args):
    path = args.batch or DOWNLOAD_BATCH_PATH
    data = load_batch(path)
    print("Tasks:", len(data.get("tasks",[])))
    for t in data.get("tasks",[])[:5]:
        print("-", t.get("spotify_id"), t.get("title"))

def clear(args):
    path = args.batch or DOWNLOAD_BATCH_PATH
    save_batch(path, {"version":1,"generated_by":"download_tasks.py",
                      "generated_at":datetime.datetime.utcnow().isoformat()+"Z",
                      "tasks":[]})
    print("Cleared batch.")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers()

    ap_info = sub.add_parser("info")
    ap_info.add_argument("--batch")
    ap_info.set_defaults(func=info)

    ap_add = sub.add_parser("add-track")
    ap_add.add_argument("--batch")
    ap_add.add_argument("--spotify-id", required=True)
    ap_add.add_argument("--artist", required=True)
    ap_add.add_argument("--album", required=True)
    ap_add.add_argument("--year", type=int, required=True)
    ap_add.add_argument("--title", required=True)
    ap_add.add_argument("--priority", type=int, default=5)
    ap_add.add_argument("--source", default="manual")
    ap_add.set_defaults(func=add_track)

    ap_clear = sub.add_parser("clear")
    ap_clear.add_argument("--batch")
    ap_clear.set_defaults(func=clear)

    args = ap.parse_args()
    if hasattr(args,"func"):
        args.func(args)
    else:
        ap.print_help()

if __name__=="__main__":
    main()
