"""
OpenAlex: все публикации 2020–2026, где хотя бы один автор аффилирован с казахстанским вузом,
и профили этих авторов.

Шаги (каждый можно перезапускать — продолжит с места остановки):
    python -m collectors.openalex_kz institutions
    python -m collectors.openalex_kz works
    python -m collectors.openalex_kz authors      # нужен OPENALEX_API_KEY в .env (лимит без ключа ~1000 запросов/день)

Вуз = организация OpenAlex с country_code=KZ и type=education, кроме EXCLUDE (школы и НИИ).
"""

import json
import os
import sys
import time

from collectors.common import RAW_DIR, YEAR_FROM, YEAR_TO, State, append_jsonl, get_json, load_env, read_jsonl

OUT = os.path.join(RAW_DIR, "openalex")
BASE = "https://api.openalex.org"
EXCLUDE = {
    "I4405260809",  # Nazarbayev Intellectual Schools и другие школы
    "I4210153665",  # Institute of Philosophy, Political Science and Religious Studies — НИИ
    "I4405258375",  # Scientific Research International Institute of Postgraduate Education — НИИ
}
WORK_FIELDS = ("id,doi,title,publication_year,publication_date,type,language,cited_by_count,counts_by_year,"
               "authorships,primary_location,open_access,topics,keywords,referenced_works_count,fwci,"
               "citation_normalized_percentile,biblio,indexed_in")
AUTHOR_FIELDS = ("id,display_name,orcid,works_count,cited_by_count,summary_stats,counts_by_year,"
                 "affiliations,last_known_institutions,topics")


def params(**kw):
    p = dict(kw)
    key = os.environ.get("OPENALEX_API_KEY")
    if key:
        p["api_key"] = key
    if os.environ.get("OPENALEX_EMAIL"):
        p["mailto"] = os.environ["OPENALEX_EMAIL"]
    return p


def short(oa_id):
    return oa_id.rsplit("/", 1)[-1] if oa_id else None


def fetch(path, **kw):
    status, data, _ = get_json(f"{BASE}/{path}", params(**kw))
    if status != 200:
        raise RuntimeError(f"OpenAlex {path}: HTTP {status} {str(data)[:300]}")
    return data


def step_institutions():
    data = fetch("institutions", filter="country_code:KZ,type:education", per_page=200,
                 select="id,display_name,display_name_alternatives,display_name_acronyms,ror,"
                        "works_count,cited_by_count,geo,lineage")
    unis = [i for i in data["results"] if short(i["id"]) not in EXCLUDE]
    json.dump(unis, open(os.path.join(OUT, "institutions.json"), "w"), ensure_ascii=False, indent=1)
    print(f"Вузов: {len(unis)} (исключено {len(data['results']) - len(unis)})")


def university_ids():
    return [short(i["id"]) for i in json.load(open(os.path.join(OUT, "institutions.json")))]


def step_works():
    if os.environ.get("OPENALEX_API_KEY"):
        works_cursor()
    else:
        works_paged()


def works_paged():
    """Без ключа курсор запрещён, но page= работает до 10 000 записей на запрос:
    режем по годам, а если в срезе больше 10 000 — делим список вузов пополам."""
    state = State(os.path.join(OUT, "works_paged_state.json"))
    path = os.path.join(OUT, "works.jsonl")
    done = set(state.get("done", []))
    queue = [(y, university_ids()) for y in range(YEAR_FROM, YEAR_TO + 1)]
    while queue:
        year, ids = queue.pop(0)
        key = f"{year}:{','.join(ids)}"
        if key in done:
            continue
        flt = f"authorships.institutions.id:{'|'.join(ids)},publication_year:{year}"
        first = fetch("works", filter=flt, per_page=200, page=1, select=WORK_FIELDS)
        total = first["meta"]["count"]
        if total > 10000 and len(ids) > 1:
            queue[:0] = [(year, ids[:len(ids) // 2]), (year, ids[len(ids) // 2:])]
            continue
        append_jsonl(path, first["results"])
        for page in range(2, min(50, -(-total // 200)) + 1):
            data = fetch("works", filter=flt, per_page=200, page=page, select=WORK_FIELDS)
            append_jsonl(path, data["results"])
            time.sleep(0.1)
        done.add(key)
        state.set("done", sorted(done))
        print(f"  {year}: {len(ids)} вузов — {total:,} работ", flush=True)
    print("Публикации собраны (возможны дубли между срезами — убираются при объединении).")


def works_cursor():
    ids = university_ids()
    state = State(os.path.join(OUT, "works_state.json"))
    path = os.path.join(OUT, "works.jsonl")
    # фильтр OR по 87 вузам и годам; курсорная пагинация, курсор сохраняется после каждой страницы
    flt = f"authorships.institutions.id:{'|'.join(ids)},publication_year:{YEAR_FROM}-{YEAR_TO}"
    cursor = state.get("cursor", "*")
    if cursor is None:
        print("Публикации уже собраны.")
        return
    got = state.get("count", 0)
    while cursor:
        data = fetch("works", filter=flt, per_page=200, cursor=cursor, select=WORK_FIELDS)
        append_jsonl(path, data["results"])
        got += len(data["results"])
        cursor = data["meta"].get("next_cursor") if data["results"] else None
        state.set("cursor", cursor)
        state.set("count", got)
        state.set("total", data["meta"]["count"])
        print(f"  works: {got:,}/{data['meta']['count']:,}", flush=True)
        time.sleep(0.1)
    print("Публикации собраны.")


def step_authors():
    if not os.environ.get("OPENALEX_API_KEY"):
        print("Внимание: нет OPENALEX_API_KEY — без ключа дневной лимит ~1000 запросов на IP.")
    unis = set(university_ids())
    wanted = set()
    for w in read_jsonl(os.path.join(OUT, "works.jsonl")):
        for a in w.get("authorships", []):
            if a.get("author", {}).get("id") and any(short(i.get("id")) in unis for i in a.get("institutions", [])):
                wanted.add(short(a["author"]["id"]))
    path = os.path.join(OUT, "authors.jsonl")
    done = {short(a["id"]) for a in read_jsonl(path)}
    todo = sorted(wanted - done)
    print(f"Авторов из вузов KZ: {len(wanted):,}; уже скачано {len(done):,}; осталось {len(todo):,}")
    for k in range(0, len(todo), 100):
        batch = todo[k:k + 100]
        data = fetch("authors", filter="openalex:" + "|".join(batch), per_page=100, select=AUTHOR_FIELDS)
        append_jsonl(path, data["results"])
        if k % 2000 == 0:
            print(f"  authors: {len(done) + k + len(batch):,}/{len(wanted):,}", flush=True)
        time.sleep(0.1)
    print("Профили авторов собраны.")


def main():
    load_env()
    os.makedirs(OUT, exist_ok=True)
    steps = sys.argv[1:] or ["institutions", "works", "authors"]
    for s in steps:
        {"institutions": step_institutions, "works": step_works, "authors": step_authors}[s]()


if __name__ == "__main__":
    main()
