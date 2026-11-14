"""Create one course and ingest every PDF in seed/material/ as a class day.

    python seed/seed_course.py                                   # sample course if seed/material is empty
    python seed/seed_course.py --course "Analysis II" --lecturer "Prof. Rossi"
    python seed/seed_course.py --keep                            # don't wipe the database first

PDFs are processed in filename order (name them 01_..., 02_..., ...). The class-day title is taken
from the filename: "02_Linear_regression.pdf" -> "Linear regression".
"""
import argparse
import re
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import UPLOAD_DIR, execute, init_db, query_one, reset_db  # noqa: E402
from app.ingest import process_lecture  # noqa: E402
from app.llm import MODEL, PROVIDER  # noqa: E402
from seed import sample_pdfs  # noqa: E402

MATERIAL = ROOT / "seed" / "material"


def title_from_filename(p: Path) -> str:
    stem = re.sub(r"^\d+[\s_\-.]*", "", p.stem)
    return stem.replace("_", " ").strip() or p.stem


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--course", default=None)
    ap.add_argument("--lecturer", default=None)
    ap.add_argument("--keep", action="store_true", help="keep existing data instead of resetting the DB")
    args = ap.parse_args()

    pdfs = sorted(MATERIAL.glob("*.pdf"))
    using_sample = not pdfs
    if using_sample:
        print("seed/material/ is empty -> generating the sample 'Introduction to Machine Learning' slides")
        sample_dir = ROOT / "data" / "sample_material"
        pdfs = sample_pdfs.generate(sample_dir)

    course_name = args.course or (sample_pdfs.SAMPLE_COURSE if using_sample else "My Course")
    lecturer = args.lecturer or (sample_pdfs.SAMPLE_LECTURER if using_sample else "Lecturer")

    if args.keep:
        init_db()
    else:
        reset_db()
    for f in UPLOAD_DIR.glob("*.pdf"):
        if not args.keep:
            f.unlink()

    print(f"LLM: {PROVIDER}:{MODEL}")
    cid = execute("INSERT INTO courses (name, lecturer_name) VALUES (?,?)", (course_name, lecturer))
    start = date.today() - timedelta(days=7 * (len(pdfs) - 1))
    for i, pdf in enumerate(pdfs, 1):
        lid = execute("INSERT INTO lectures (course_id, number, title, date, status) VALUES (?,?,?,?,'uploaded')",
                      (cid, i, title_from_filename(pdf), (start + timedelta(days=7 * (i - 1))).isoformat()))
        dest = UPLOAD_DIR / f"{lid}.pdf"
        shutil.copy(pdf, dest)
        execute("UPDATE lectures SET slides_path=? WHERE id=?", (str(dest), lid))
        print(f"  [{i}/{len(pdfs)}] {pdf.name} -> lecture {lid} ... ", end="", flush=True)
        process_lecture(lid)
        print(query_one("SELECT status FROM lectures WHERE id=?", (lid,))["status"])

    print(f"\nDone. Course id {cid}. Start the app and open http://localhost:8000/course/{cid}")


if __name__ == "__main__":
    main()
