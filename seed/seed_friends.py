"""Make a random friends network between students. Run AFTER the students exist (seed_fake_activity.py).

    python seed/seed_friends.py                    # replaces all friendships
    python seed/seed_friends.py --min 1 --max 8 --pending 2 --seed 3
    python seed/seed_friends.py --keep             # add to the existing network instead of replacing it

Every student gets a random number of friends between --min and --max (mostly classmates, sometimes
someone from another course), plus 0..--pending incoming friend requests still waiting for an answer.
No LLM calls.
"""
import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import connect, init_db  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=1, help="fewest friends per student")
    ap.add_argument("--max", type=int, default=8, help="most friends per student")
    ap.add_argument("--pending", type=int, default=2, help="up to this many open requests per student")
    ap.add_argument("--classmates", type=float, default=0.85, help="share of friends picked from the same courses")
    ap.add_argument("--keep", action="store_true", help="keep existing friendships")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    init_db()
    with connect() as conn:
        students = [r[0] for r in conn.execute("SELECT id FROM users WHERE role='student'")]
        if len(students) < 2:
            sys.exit("Need at least 2 students. Run seed/seed_fake_activity.py first.")
        if not args.keep:
            conn.execute("DELETE FROM friendships")
        courses: dict[int, set[int]] = {}
        for uid, cid in conn.execute("SELECT user_id, course_id FROM enrollments"):
            courses.setdefault(uid, set()).add(cid)
        classmates = {s: [o for o in students if o != s and courses.get(s, set()) & courses.get(o, set())]
                      for s in students}

        pairs = {frozenset(r) for r in conn.execute("SELECT requester_id, addressee_id FROM friendships")}
        degree = {s: 0 for s in students}
        for p in pairs:
            for s in p:
                degree[s] = degree.get(s, 0) + 1
        hi = min(args.max, len(students) - 1)
        target = {s: rng.randint(min(args.min, hi), hi) for s in students}

        def pick(s: int) -> int | None:
            pool = classmates[s] if classmates[s] and rng.random() < args.classmates else students
            cand = [o for o in pool if o != s and frozenset((s, o)) not in pairs]
            # prefer people who still want more friends, so degrees end up close to their targets
            wanting = [o for o in cand if degree[o] < target[o]]
            return rng.choice(wanting or cand) if cand else None

        accepted = pending = 0
        order = students[:]
        rng.shuffle(order)
        for s in order:
            for _ in range(max(0, target[s] - degree[s])):
                o = pick(s)
                if o is None:
                    break
                a, b = rng.sample([s, o], 2)  # who asked first doesn't matter, but make it look natural
                conn.execute("INSERT INTO friendships (requester_id, addressee_id, status) VALUES (?,?,'accepted')", (a, b))
                pairs.add(frozenset((s, o)))
                degree[s] += 1
                degree[o] += 1
                accepted += 1
        for s in order:
            for _ in range(rng.randint(0, args.pending)):
                o = pick(s)
                if o is None:
                    break
                conn.execute("INSERT INTO friendships (requester_id, addressee_id, status) VALUES (?,?,'pending')", (o, s))
                pairs.add(frozenset((s, o)))
                pending += 1

    degs = sorted(degree.values())
    print(f"{len(students)} students: {accepted} new friendships, {pending} pending requests. "
          f"Friends per student: min {degs[0]}, median {degs[len(degs) // 2]}, max {degs[-1]}.")


if __name__ == "__main__":
    main()
