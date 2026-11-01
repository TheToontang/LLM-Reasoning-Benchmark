import csv
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google import genai


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

load_dotenv()

MODEL_ID = "gemini-3.8-flash"
INPUT_CSV = Path("questions.csv")
OUTPUT_CSV = Path("results") / "experiment_results.csv"

MAX_ATTEMPTS = 5
BASE_RETRY_SECONDS = 5
REQUEST_INTERVAL_SECONDS = 2

FIELDNAMES = [
    "Question_ID",
    "Category",
    "Variant",
    "Correct_Answer",
    "Model_Answer",
    "Evaluation",
    "Raw_Response",
    "Latency_Seconds",
    "Status",
    "Error",
    "Model_ID",
    "Timestamp_UTC",
]

VALID_ANSWERS = {"A", "B", "C", "D"}
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def find_input_file():
    """Find the dataset without changing its column names."""
    candidates = [
        INPUT_CSV,
        Path("dataset") / "questions.csv",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "Could not find questions.csv. Put it in the project root "
        "or inside the dataset/ folder."
    )


def normalize_row(row):
    """Normalize header spelling while retaining the dataset structure."""
    return {
        str(key).strip().lower(): (value or "").strip()
        for key, value in row.items()
        if key is not None
    }


def load_questions(csv_path):
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError("The questions CSV has no header row.")

        questions = [normalize_row(row) for row in reader]

    required = {
        "id", "category", "variant", "question",
        "choice_a", "choice_b", "choice_c", "choice_d",
        "gold_answer",
    }

    if not questions:
        raise ValueError("The questions CSV contains no questions.")

    missing = required - set(questions[0].keys())
    if missing:
        raise ValueError(
            "The questions CSV is missing required columns: "
            + ", ".join(sorted(missing))
        )

    seen = set()
    for row_number, question in enumerate(questions, start=2):
        question_id = question["id"]
        variant = question["variant"].lower()
        key = (question_id, variant)

        if not question_id or not variant:
            raise ValueError(
                f"Row {row_number}: ID and Variant cannot be empty."
            )

        if key in seen:
            raise ValueError(
                f"Duplicate Question_ID + Variant found: {key}"
            )
        seen.add(key)

        gold = question["gold_answer"].strip().upper()
        if gold not in VALID_ANSWERS:
            raise ValueError(
                f"Row {row_number} ({question_id}): "
                f"gold_answer must be A, B, C, or D; got {gold!r}."
            )

        question["variant"] = variant
        question["gold_answer"] = gold

    return questions


def backup_incompatible_results(output_path):
    """
    Preserve an older CSV instead of mixing old and new column schemas.
    Returns True if a backup was made.
    """
    if not output_path.exists() or output_path.stat().st_size == 0:
        return False

    with output_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        existing_header = next(reader, [])

    if existing_header == FIELDNAMES:
        return False

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = output_path.with_name(
        f"{output_path.stem}_legacy_{timestamp}{output_path.suffix}"
    )
    shutil.copy2(output_path, backup_path)
    print(
        "-> Existing results use an older column format. "
        f"Preserved a copy at: {backup_path}"
    )
    return True


def load_existing_results(output_path):
    """Load the latest saved row for each Question_ID + Variant."""
    saved = {}

    if not output_path.exists() or output_path.stat().st_size == 0:
        return saved

    with output_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames != FIELDNAMES:
            raise ValueError(
                "The existing results file still has an incompatible header. "
                "Please keep the legacy backup and remove or rename the "
                "incompatible experiment_results.csv before running again."
            )

        for row in reader:
            key = (row["Question_ID"], row["Variant"])
            saved[key] = {field: row.get(field, "") for field in FIELDNAMES}

    return saved


def save_results(output_path, saved_results):
    """Rewrite the small results file so failed attempts can be replaced."""
    temporary_path = output_path.with_suffix(".tmp")

    with temporary_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()

        for row in saved_results.values():
            writer.writerow(row)

    temporary_path.replace(output_path)


def is_completed(row):
    """Only a successful API call with a parsed A-D answer is complete."""
    return (
        row.get("Status") == "success"
        and row.get("Model_Answer", "").upper() in VALID_ANSWERS
    )


def extract_answer(raw_response):
    """
    Extract a single unambiguous A-D answer.
    Examples accepted: 'B', '(B)', 'Answer: B', 'The answer is B.'
    Ambiguous responses such as 'A or B' become UNKNOWN.
    """
    if not raw_response:
        return "UNKNOWN"

    text = raw_response.strip().upper()

    # Prefer a response that consists of a single letter, optionally wrapped.
    if re.fullmatch(r"[\s\(\[\{]*([ABCD])[\s\)\]\}.!]*", text):
        match = re.search(r"[ABCD]", text)
        return match.group(0)

    # Otherwise accept exactly one standalone A-D token in the response.
    matches = re.findall(r"(?<![A-Z])([ABCD])(?![A-Z])", text)
    unique_answers = set(matches)

    if len(unique_answers) == 1:
        return unique_answers.pop()

    return "UNKNOWN"


def get_status_code(error):
    """Read the HTTP status code exposed by google-genai exceptions."""
    code = getattr(error, "code", None)
    if code is None:
        code = getattr(error, "status_code", None)

    try:
        return int(code)
    except (TypeError, ValueError):
        return None


def call_model(client, prompt):
    """
    Call Gemini with bounded retries.
    Retries server errors and common temporary/rate-limit HTTP errors.
    """
    last_error = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.perf_counter()

        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=prompt,
                config={"temperature": 0},
            )
            latency = time.perf_counter() - started
            raw_response = (response.text or "").strip()

            return {
                "api_success": True,
                "raw_response": raw_response,
                "latency": latency,
                "error": "",
            }

        except Exception as error:
            latency = time.perf_counter() - started
            status_code = get_status_code(error)
            last_error = f"{type(error).__name__}: {error}"

            retryable = (
                status_code in RETRYABLE_STATUS_CODES
                or type(error).__name__ == "ServerError"
            )

            if retryable and attempt < MAX_ATTEMPTS:
                wait_seconds = BASE_RETRY_SECONDS * (2 ** (attempt - 1))
                print(
                    f"  -> Temporary API error "
                    f"({status_code or type(error).__name__}). "
                    f"Retrying in {wait_seconds}s "
                    f"({attempt}/{MAX_ATTEMPTS})..."
                )
                time.sleep(wait_seconds)
                continue

            return {
                "api_success": False,
                "raw_response": "",
                "latency": latency,
                "error": last_error,
            }

    return {
        "api_success": False,
        "raw_response": "",
        "latency": 0.0,
        "error": last_error or "Failed after all retry attempts.",
    }


def make_prompt(question):
    choices = (
        f"A. {question['choice_a']}\n"
        f"B. {question['choice_b']}\n"
        f"C. {question['choice_c']}\n"
        f"D. {question['choice_d']}"
    )

    return (
        f"{question['question']}\n\n"
        f"{choices}\n\n"
        "Choose the single best answer. "
        "Output only one capital letter: A, B, C, or D. "
        "Do not include an explanation."
    )


def run_full_benchmark():
    csv_path = find_input_file()
    questions = load_questions(csv_path)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    backup_incompatible_results(OUTPUT_CSV)

    saved_results = load_existing_results(OUTPUT_CSV)
    completed = {
        key for key, row in saved_results.items() if is_completed(row)
    }

    print(f"Dataset: {csv_path}")
    print(f"Model: {MODEL_ID}")
    print(f"Questions in dataset: {len(questions)}")
    print(f"Already completed successfully: {len(completed)}")
    print(f"Results file: {OUTPUT_CSV}\n")

    # Create the standardized CSV header before making API requests.
    if not OUTPUT_CSV.exists():
        save_results(OUTPUT_CSV, saved_results)

    client = genai.Client()
    newly_attempted = 0

    for index, question in enumerate(questions, start=1):
        question_id = question["id"]
        category = question["category"].lower()
        variant = question["variant"]
        correct_answer = question["gold_answer"]
        key = (question_id, variant)

        if key in completed:
            print(
                f"[{index}/{len(questions)}] "
                f"Skipping {question_id} ({variant}) - already completed."
            )
            continue

        print(
            f"[{index}/{len(questions)}] "
            f"Processing {question_id} | {category} | {variant}..."
        )

        result = call_model(client, make_prompt(question))

        if result["api_success"]:
            model_answer = extract_answer(result["raw_response"])

            if model_answer in VALID_ANSWERS:
                status = "success"
                evaluation = (
                    "Correct"
                    if model_answer == correct_answer
                    else "Incorrect"
                )
                error_message = ""
            else:
                status = "unparseable"
                evaluation = "Not_Evaluated"
                error_message = (
                    "API call succeeded, but the response did not contain "
                    "one unambiguous A-D answer."
                )
        else:
            model_answer = ""
            status = "api_error"
            evaluation = "Not_Evaluated"
            error_message = result["error"]

        record = {
            "Question_ID": question_id,
            "Category": category,
            "Variant": variant,
            "Correct_Answer": correct_answer,
            "Model_Answer": model_answer,
            "Evaluation": evaluation,
            "Raw_Response": result["raw_response"],
            "Latency_Seconds": f"{result['latency']:.3f}",
            "Status": status,
            "Error": error_message,
            "Model_ID": MODEL_ID,
            "Timestamp_UTC": datetime.now(timezone.utc).isoformat(),
        }

        # Upsert by Question_ID + Variant. A failed/unparseable attempt is
        # saved for inspection, but will be retried on the next script run.
        saved_results[key] = record
        save_results(OUTPUT_CSV, saved_results)
        newly_attempted += 1

        if status == "success":
            completed.add(key)
            print(
                f"  -> Model: {model_answer} | "
                f"Correct: {correct_answer} | {evaluation}"
            )
        else:
            print(
                f"  -> Status: {status} | "
                f"Evaluation: {evaluation} | {error_message}"
            )

        if index < len(questions):
            time.sleep(REQUEST_INTERVAL_SECONDS)

    successful_count = sum(
        1 for row in saved_results.values() if is_completed(row)
    )
    error_count = sum(
        1 for row in saved_results.values()
        if row.get("Status") in {"api_error", "unparseable"}
    )

    print("\nBenchmark run finished.")
    print(f"Successful questions: {successful_count}/{len(questions)}")
    print(f"Questions needing retry/review: {error_count}")
    print(f"New attempts this run: {newly_attempted}")
    print(f"Results saved to: {OUTPUT_CSV}")

    if error_count:
        print(
            "Some questions were not successfully evaluated. "
            "You can run this script again; successful rows will be skipped "
            "and failed/unparseable rows will be attempted again."
        )


if __name__ == "__main__":
    run_full_benchmark()
