#!/usr/bin/env python3
"""테스트 커버리지 맵 생성 — 각 test 함수의 첫 docstring 줄을 추출해 출력.

순수 AST 파싱(Django/의존성 불필요). docstring이 SoT라 항상 최신.
사용: python3 scripts/gen_test_map.py   (또는 make test-map)
"""
import ast
import glob
import os

SECTIONS = [
    ("DRF", ["drf-server/apps/**/test_*.py"]),
    ("FastAPI", ["fastapi-server/tests/test_*.py"]),
]

def tests_in(path):
    try:
        tree = ast.parse(open(path).read())
    except Exception:
        return []
    out = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test"):
            doc = ast.get_docstring(n)
            line = doc.strip().splitlines()[0] if doc else "(설명 없음)"
            out.append((n.name, line))
    return out

def collect(globs):
    files = {}
    for g in globs:
        for f in sorted(glob.glob(g, recursive=True)):
            if "__pycache__" in f or os.path.basename(f) == "__init__.py":
                continue
            t = tests_in(f)
            if t:
                files[f] = t
    return files

grand = 0
detail = []
print("# 테스트 커버리지 맵\n")
for label, globs in SECTIONS:
    files = collect(globs)
    n = sum(len(v) for v in files.values())
    grand += n
    print(f"## {label} — 파일 {len(files)} · 테스트 {n}")
    for f in sorted(files):
        print(f"  {len(files[f]):>2}  {f.split('diconai/')[-1]}")
        detail.append((f, files[f]))
    print()
print(f"**합계: {grand} 테스트**\n")
print("---\n# 상세 (테스트별 검증 내용)\n")
for f, tests in detail:
    print(f"\n### {f.split('diconai/')[-1]}")
    for name, line in tests:
        print(f"- `{name}` — {line}")
