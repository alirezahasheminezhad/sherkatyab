import asyncio, tempfile, company_search as cs
cs.DB = tempfile.mkdtemp()
calls = {"s": 0, "c": 0}
async def fs(**k):
    calls["s"] += 1
    return {"total": 3, "pages": 1, "results": [
        {"company_id": "1", "name": "الف", "verified_by_company": None, "license_count": None},
        {"company_id": "2", "name": "ب", "verified_by_company": True, "license_count": 3},
        {"company_id": "3", "name": "پ"}]}
async def fc(company_id, sections, max_rows):
    calls["c"] += 1
    if calls["c"] > 2: raise RuntimeError("limit")
    return {"address": "x" + company_id}
r = asyncio.run(cs.run("ذرت", 3, False, fs, fc))
assert r["ranked"][0] == "2"  # verified + licenses beat raw capital order
assert calls == {"s": 1, "c": 3}  # 3rd call hit the limit and stopped
asyncio.run(cs.run("ذرت", 3, False, fs, fc))
assert calls["s"] == 1  # second search of same keyword is served from the cache
assert cs.load("companies")["2"]["profile"] == {"address": "x2"}
print("ok company")
