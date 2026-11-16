"""
End-to-end check of the quiz endpoints WITHOUT Moodle (development).

Runs the real FastAPI app in-process (no uvicorn needed), with the real
LLM, ChromaDB and chat database from .env, and signs every request like
Moodle does. It creates a test chat, generates a quiz, answers it, reads
the chat back, and deletes the test chat again.

Run from the api/ folder:

    python -m eval.quiz_api_check 12
    python -m eval.quiz_api_check 12 --topic "PtL-Anlagen" --count 3 --lang ru
"""

import argparse
import base64
import json
import sys
import time

from eval.run_eval import load_env_file

TEST_USER_ID = 999999   # a user id no real Moodle user has


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    p = argparse.ArgumentParser(description="Check the quiz endpoints end to end")
    p.add_argument("course_id", type=int)
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--topic", default=None)
    p.add_argument("--lang", default=None)
    args = p.parse_args()

    load_env_file()
    from fastapi.testclient import TestClient
    from settings import settings
    from middleware.auth import compute_signature
    import main as app_module

    client = TestClient(app_module.app)
    courses = base64.urlsafe_b64encode(
        json.dumps({str(args.course_id): f"Course {args.course_id}"}).encode()
    ).decode().rstrip("=")

    def call(method: str, path: str, body=None):
        raw = json.dumps(body).encode() if body is not None else b""
        ts = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "X-Timestamp": ts,
            "X-User-Id": str(TEST_USER_ID),
            "X-Enrolled-Courses": courses,
            "X-Signature": compute_signature(
                settings.MOODLE_SECRET, ts, method, path.split("?")[0],
                str(TEST_USER_ID), courses, raw,
            ),
        }
        r = client.request(method, path, content=raw, headers=headers)
        if r.status_code >= 400:
            print(f"  !! {method} {path} -> {r.status_code}: {r.text[:300]}")
        return r

    ok = True
    session_id = call("POST", "/sessions", {"course_id": args.course_id}).json()["session_id"]
    print(f"test chat {session_id} (user {TEST_USER_ID}, course {args.course_id})")
    try:
        t = time.perf_counter()
        r = call("POST", f"/sessions/{session_id}/quiz", {
            "scope": "course", "count": args.count, "topic": args.topic, "language": args.lang,
        })
        if r.status_code != 200:
            return
        created = r.json()
        quiz_msg = created["quiz"]
        quiz = quiz_msg["quiz"]
        print(f"1. quiz created in {time.perf_counter() - t:.1f}s: {len(quiz['questions'])} questions, "
              f"language {quiz['language']}, chat title {created['title']!r}")

        leaked = [i for i, q in enumerate(quiz["questions"]) if "correct" in q or "explanation" in q]
        print(f"2. right answers hidden before answering: {'yes' if not leaked else 'NO, questions ' + str(leaked)}")
        ok &= not leaked

        for i, q in enumerate(quiz["questions"]):
            r = call("POST", f"/sessions/{session_id}/quiz/{quiz_msg['id']}/answer",
                     {"question_index": i, "answer": [0]})
            res = r.json()["result"]
            right = "; ".join(q["options"][c] for c in res["correct"])
            print(f"   Q{i + 1}: {q['question']}\n       chose A -> {'right' if res['is_correct'] else 'wrong'}"
                  f" (right: {right})\n       source: {res['source']}")
        final = r.json()["quiz"]
        print(f"3. all answered: finished={final['finished']}, score {final['score']}/{len(final['questions'])}")
        ok &= final["finished"]

        again = call("POST", f"/sessions/{session_id}/quiz/{quiz_msg['id']}/answer",
                     {"question_index": 0, "answer": [1]}).json()["result"]["answer"]
        print(f"4. second answer to Q1 ignored: {'yes' if again == [0] else 'NO'}")
        ok &= again == [0]

        messages = call("GET", f"/sessions/{session_id}/messages?cached_only=true").json()
        types = [m["content_type"] for m in messages]
        restored = messages[-1]["quiz"]["answered"] if messages else 0
        print(f"5. chat read back: {types}, answers restored: {restored}")
        ok &= types == ["quiz_request", "quiz"] and restored == len(final["questions"])
    finally:
        call("DELETE", f"/sessions/{session_id}")
        print(f"test chat deleted")
    print("\nRESULT:", "OK" if ok else "PROBLEMS (see above)")


if __name__ == "__main__":
    main()
