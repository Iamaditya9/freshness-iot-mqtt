import json
import os
import urllib.request
import urllib.error


API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-3.8-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"


def analyze_results_with_gemini(summary_csv_path: str = "results/summary_table.csv"):
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. In PowerShell run:\n"
            '  $env:GEMINI_API_KEY="YOUR_KEY_HERE"'
        )

    with open(summary_csv_path, "r", encoding="utf-8") as f:
        csv_text = f.read()

    system_instruction = (
        "You are a computer networks researcher analyzing controlled MQTT IoT "
        "experiment results comparing FIFO vs Freshness-Aware queuing. "
        "Be objective: report both improvements and regressions/trade-offs. "
        "Return ONLY valid JSON with keys: "
        "'executive_summary', 'where_freshness_wins', 'tradeoffs_and_regressions', "
        "'operating_recommendations', and 'limitations_to_note'."
    )

    prompt = (
        "Analyze the following aggregated MQTT experiment results (CSV) and "
        "produce a structured technical evaluation for a university networking report:\n\n"
        f"{csv_text}"
    )

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            raw_json_text = result["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw_json_text)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API HTTP {e.code}: {err_body}") from e

    out_path = "results/gemini_findings.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2)

    print(f"Saved structured Gemini analysis to {out_path}\n")
    print(json.dumps(parsed, indent=2))


if __name__ == "__main__":
    analyze_results_with_gemini()