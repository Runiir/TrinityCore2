"""Replay labeled advice cases; expected answers never enter model state."""
import argparse
import json
from pathlib import Path

from tools.raid_program.bot_improvement_advice import review, encoded, digest


def evaluate(cases, output, **kwargs):
    output.mkdir(parents=True, exist_ok=False)
    (output / "cases.json").write_bytes(encoded(cases) + b"\n")
    results = []
    for index, case in enumerate(cases):
        summary = review(case["comparison"], output / str(index), **kwargs)
        for row in summary["reviews"]:
            suggestion = row["suggestion"]
            choice = suggestion["choice"] if suggestion else None
            results.append({"case": case["id"], "basis": case["basis"],
                            "provider": row["provider"], "status": row["status"],
                            "expected": case["expected"], "choice": choice,
                            "correct": choice in case["expected"] if suggestion else None})
    totals = {}
    for provider in {r["provider"] for r in results}:
        rows = [r for r in results if r["provider"] == provider]
        totals[provider] = {"total": len(rows), "reviewed": sum(r["correct"] is not None for r in rows),
                            "correct": sum(r["correct"] is True for r in rows),
                            "incorrect": sum(r["correct"] is False for r in rows),
                            "not_reviewed": sum(r["correct"] is None for r in rows)}
    result = {"schema": "bot_advice_evaluation_v1", "cases_sha256": digest(cases),
              "training_eligible": False, "acceptance_authority": False,
              "totals": totals, "results": results}
    (output / "summary.json").write_bytes(encoded(result) + b"\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--backend", choices=("local", "hosted", "both"), default="both")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    result = evaluate(json.loads(args.cases.read_text()), args.output,
                      backend=args.backend, env_file=args.env_file)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
