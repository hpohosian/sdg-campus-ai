"""
Converts the manual test sheet (chatbot_test.xlsx) into eval/questions.json,
the dataset run_eval.py works from.

Run from the api/ folder:
    python -m eval.build_dataset path\\to\\chatbot_test.xlsx

Re-run it whenever questions are added or changed in the sheet. Expected
columns (row 1 = header, same order as the sheet):
    A Chat / mode | B Course | C Group | D Language | E Question
    F Expected response | G Source (file, PDF) | H Chatbot response
    I Right? | J Is the source correct?

Column B decides the search scope:
    8 / 11 / 12 ...      -> course mode (that course selected in the picker)
    "global"             -> global mode, user enrolled in ENROLLED_COURSES
    "without enrolling"  -> user enrolled in nothing (must get no course content)

Needs openpyxl (pip install openpyxl) — only this builder, not run_eval.py.
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

# Courses the test user is enrolled in for the "global" rows.
ENROLLED_COURSES = [8, 11, 12]

# Shown in citations exactly like production (format_course_link).
COURSE_NAMES = {
    8: "Didaktische Zugänglichkeit",
    11: "Industrie, Innovation und Infrastruktur",
    12: "PtX-Lab-Challenge",
}

# Expected-response text that is broken in the sheet, by question number.
EXPECTED_OVERRIDES = {
    39: "The bot must NOT provide or quote the content of Course 12 "
        "(an answer based on general knowledge, without referencing the "
        "course document, is permissible).",
}

# "Evidence" = regexes that the chunk holding the answer must ALL match
# (case-insensitive). With it run_eval.py checks retrieval per CHUNK, not
# only per PDF: the right PDF can be retrieved with the wrong passage.
# Written from the expected answers, in the language of the PDF. If a run
# reports "evidence_not_in_index" for a question although the text IS in
# the PDF, the pattern is too strict — fix it here and rebuild.
EVIDENCE = {
    1: [r"halbe[n]?\s+seite"],
    2: [r"45\s*(?:-|–|bis)\s*90"],
    3: [r"inform", r"plan", r"kontroll"],
    4: [r"august\s+2021|1\.\s*8\.\s*2021|01\.08\.2021"],
    5: [r"1[.,]?\s?061"],
    6: [r"\b218\b"],
    7: [r"2008", r"blog"],
    8: [r"2009", r"2012", r"2014"],
    10: [r"\b159\b"],
    11: [r"hannover", r"schuldschein"],
    12: [r"[öo]stersund"],
    13: [r"baker"],
    14: [r"vuca"],
    15: [r"markt", r"hierarchie"],
    16: [r"institut f[üu]r soziologie"],
    17: [r"2021", r"gegr[üu]nd|gr[üu]ndung"],
    18: [r"schwarze\s+pumpe|green\s+fuels"],
    19: [r"werlte"],
    20: [r"investitionsentscheid"],
    21: [r"[öo]konomisch|wirtschaftlich", r"politisch"],
    22: [r"pilot"],
    23: [r"internship"],
    24: [r"antifoundational"],
    25: [r"10\s*(?:-|–|to)\s*40"],
    26: [r"2007", r"\beib\b|europ[äa]ische\s+investitionsbank|european\s+investment\s+bank"],
    27: [r"werlte"],
    28: [r"europe\s+engage"],
    29: [r"learning\s+to\s+serve"],
    30: [r"mitarbeiter", r"\b20\b"],
    31: [r"konsensprinzip"],
    36: [r"werlte|nextgate"],
}

# Key facts the answer MUST contain — only what the question asks, no
# background. The judge checks each one separately and has to quote the
# answer as proof; the verdict is then computed from the count (all ->
# correct, at least half -> partial, else wrong). Much more stable than one
# overall "is this right?" call. Questions without key facts (refusals,
# false premise, scope checks) are judged on the expected BEHAVIOUR.
KEY_FACTS = {
    1: ["about half a page long", "limited to 2-3 moral principles"],
    2: ["at most 30 people", "45-90 minutes"],
    3: ["inform(ation)", "plan(ning)", "decide/decision", "carry out/execute",
        "check/control", "evaluate/reflect"],
    4: ["1 August 2021"],
    5: ["1,061 pupils", "grades 7, 9 and 12"],
    6: ["218 minutes a day"],
    7: ["2008", "through a blog post"],
    8: ["2009, 2012 and 2014", "the second report is about learning processes in ESD"],
    10: ["about 159 billion euros"],
    11: ["Hannover", "100 million euros"],
    12: ["about 50,000 inhabitants", "about 80 million euros"],
    13: ["about 6 basis points on average", "about 26 basis points with external certification"],
    14: ["volatility", "uncertainty", "complexity", "ambiguity"],
    15: ["sociological view: networks as a third coordination form beside market and hierarchy",
         "Science and Technology Studies / socio-technical (heterogeneous) networks",
         "formal network analysis"],
    16: ["Institute of Sociology (Institut für Soziologie)", "RWTH Aachen University"],
    17: ["March 2021", "founded by ZUG gGmbH", "located in Cottbus"],
    18: ["Green Fuels Lausitz (Schwarze Pumpe)", "Green MeOH (Stade)", "200,000 t/year each"],
    19: ["360 t/year", "in operation since 2021"],
    20: ["Shell Rheinland Raffinerie (Cologne)"],
    21: ["a long-term (ambitious) and a short-term standard",
         "economic and political dimensions are not included"],
    22: ["first in a pilot certification"],
    23: ["service learning: deepen understanding of theory through community service and reflection",
         "internship: acquire specific career skills"],
    24: ["technical", "cultural", "political", "antifoundational"],
    25: ["at least half a semester", "about 10-40 hours"],
    26: ["2007", "European Investment Bank (EIB)"],
    27: ["360 t/year"],
    28: ["pedagogical approach integrating community service into the curriculum",
         "students earn academic credit for the learning",
         "based on reflection / experiential learning"],
    29: ["Maureen E. Kenny"],
    30: ["about 20 employees"],
    31: ["dual principle", "occupational principle (Berufsprinzip)", "consensus principle (Konsensprinzip)"],
}

# Russian / Ukrainian versions of existing questions (the course PDFs are
# only German/English). Same scope, expected answer, evidence and key facts
# as the base question, so retrieval for the SAME question can be compared
# across languages: compare with --no-retrieval-translation and without.
# (base question id, language, question text)
TRANSLATED_VARIANTS = [
    (2, "ru", "Для какого размера группы и какой продолжительности рассчитан метод World Café?"),
    (2, "uk", "Для якого розміру групи та якої тривалості розрахований метод World Café?"),
    (4, "ru", "С какого момента стандартная позиция профессионального обучения «Охрана окружающей среды» дополнена аспектом «Устойчивое развитие»?"),
    (4, "uk", "З якого часу стандартну позицію професійного навчання «Охорона довкілля» доповнено аспектом «Сталий розвиток»?"),
    (6, "ru", "Сколько минут в день 14–19-летние пользуются интернетом согласно онлайн-исследованию ARD/ZDF 2013 года?"),
    (6, "uk", "Скільки хвилин на день 14–19-річні користуються інтернетом за онлайн-дослідженням ARD/ZDF 2013 року?"),
    (10, "ru", "Каков объём отставания муниципальных инвестиций по данным KfW-Kommunalpanel 2018?"),
    (10, "uk", "Яким є обсяг відставання муніципальних інвестицій за даними KfW-Kommunalpanel 2018?"),
    (14, "ru", "Что означает аббревиатура VUCA?"),
    (14, "uk", "Що означає абревіатура VUCA?"),
    (17, "ru", "Когда и кем была основана PtX Lab Lausitz и где она находится?"),
    (17, "uk", "Коли і ким було засновано PtX Lab Lausitz і де вона розташована?"),
    (24, "ru", "Какие четыре перспективы на service-learning выделяет Butin?"),
    (24, "uk", "Які чотири перспективи на service-learning виокремлює Butin?"),
]

OUT_PATH = Path(__file__).parent / "questions.json"


def source_key(raw: str | None) -> str | None:
    """
    Turns the sheet's free-text source cell into a matching key, e.g.
        "KfW_Fokus-...Green-Bonds.pdf (course 11)"  -> "kfwfokus"
        "5547_Schulische_Rahmenbedingungen.pdf"     -> "schulischerahmenbedingungen"
    run_eval.py applies normalize() to the real chunk source and checks
    that the key is a substring of it.
    """
    if not raw:
        return None
    text = raw.strip()
    if text in {"—", "-", ""} or text.startswith("("):
        return None
    text = re.sub(r"\(course \d+\)", "", text, flags=re.I).strip()
    text = text.split("...")[0]          # "Häußling_InnovationNetzwerke...pdf"
    text = re.sub(r"\.pdf$", "", text, flags=re.I)
    text = re.sub(r"^\d+_", "", text)     # "5547_Schulische..." -> the bot drops it
    key = normalize(text)
    return key or None


def normalize(text: str) -> str:
    """Lowercase, umlauts folded, ß -> ss, everything except a-z0-9 removed."""
    text = text.replace("ß", "ss").replace("ẞ", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\.pdf\b", "", text.lower())
    return re.sub(r"[^a-z0-9]", "", text)


def parse_scope(cell) -> dict:
    if isinstance(cell, (int, float)):
        return {"mode": "course", "course_id": int(cell)}
    value = str(cell).strip().lower()
    if value.isdigit():
        return {"mode": "course", "course_id": int(value)}
    if value == "global":
        return {"mode": "global", "course_ids": ENROLLED_COURSES}
    if "without" in value:
        return {"mode": "unenrolled"}
    raise ValueError(f"Unknown course/scope value: {cell!r}")


def main(xlsx_path: str) -> None:
    import openpyxl  # imported here so run_eval.py can use normalize() without it

    sheet = openpyxl.load_workbook(xlsx_path, data_only=True).active
    questions = []

    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not row or not row[4]:
            continue
        number = len(questions) + 1
        chat, course, group, lang, question, expected, source = row[:7]
        manual_answer, manual_right, manual_source_ok = (list(row[7:10]) + [None] * 3)[:3]

        scope = parse_scope(course)
        key = source_key(source)

        # What the retrieval step is checked against:
        #   "hit"        -> the expected source must be among the chunks sent to the LLM
        #   "no_context" -> no chunks at all (user not enrolled)
        #   None         -> nothing to check (no-answer questions, course-scope refusals)
        if scope["mode"] == "unenrolled":
            retrieval_check = "no_context"
        elif key and group != "Access/Scope":
            retrieval_check = "hit"
        else:
            retrieval_check = None

        questions.append({
            "id": number,
            "chat": chat,
            "scope": scope,
            "group": group,
            "lang": (lang or "").strip().lower(),
            "question": question.strip(),
            "expected": EXPECTED_OVERRIDES.get(number, (expected or "").strip()),
            "source_raw": source,
            "source_key": key,
            "evidence": EVIDENCE.get(number, []) if retrieval_check == "hit" else [],
            "key_facts": KEY_FACTS.get(number, []),
            "retrieval_check": retrieval_check,
            "manual": {
                "answer": manual_answer,
                "right": manual_right,
                "source_ok": manual_source_ok,
            },
        })

    by_id = {q["id"]: q for q in questions}
    for base_id, lang, text in TRANSLATED_VARIANTS:
        base = by_id[base_id]
        questions.append({
            **base,
            "id": len(questions) + 1,
            "chat": f"Translated variants ({lang})",
            "group": "Cross-language",
            "lang": lang,
            "question": text,
            "base_id": base_id,
            "manual": {"answer": None, "right": None, "source_ok": None},
        })

    OUT_PATH.write_text(
        json.dumps(
            {"course_names": COURSE_NAMES, "questions": questions},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"{len(questions)} questions -> {OUT_PATH}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m eval.build_dataset path/to/chatbot_test.xlsx")
    main(sys.argv[1])
    