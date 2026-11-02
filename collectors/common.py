"""Общие утилиты сборщиков: HTTP с повторами, JSONL-файлы, состояние для продолжения после обрыва."""

import json
import os
import time

import requests

RAW_DIR = os.path.join("data", "raw")
PROCESSED_DIR = os.path.join("data", "processed")
YEAR_FROM, YEAR_TO = 2020, 2026

def load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_json(url, params=None, headers=None, retries=6, timeout=60, ok_codes=(200,)):
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            wait = min(2 ** attempt * 2, 120)
            print(f"    сеть: {e.__class__.__name__}, жду {wait} c")
            time.sleep(wait)
            continue
        if r.status_code in ok_codes:
            try:
                return r.status_code, r.json(), r.headers
            except ValueError:
                wait = min(2 ** attempt * 2, 120)
                print(f"    битый JSON, жду {wait} c")
                time.sleep(wait)
                continue
        if r.status_code == 429 or r.status_code >= 500:
            wait = min(2 ** attempt * 2, 120)
            print(f"    HTTP {r.status_code}, жду {wait} c")
            time.sleep(wait)
            continue
        try:
            body = r.json()
        except ValueError:
            body = {"text": r.text[:500]}
        return r.status_code, body, r.headers
    return None, None, {}


class State:

    def __init__(self, path):
        self.path = path
        self.data = json.load(open(path)) if os.path.exists(path) else {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        tmp = self.path + ".tmp"
        json.dump(self.data, open(tmp, "w"), ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)


def append_jsonl(path, records):
    with open(path, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_jsonl(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue   # недописанная строка после обрыва
