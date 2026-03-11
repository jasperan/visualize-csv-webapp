import json
import re
import requests
import pandas as pd
import traceback


def chat_with_data(question, df, ollama_url, model, column_info=None):
    """Use Ollama to answer a natural-language question about a DataFrame.

    The LLM generates Pandas code, which is executed safely against the data.
    Returns a dict with 'answer', optional 'code', optional 'table', and optional 'chart'.
    """
    columns_desc = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        sample = df[col].dropna().head(3).tolist()
        columns_desc.append(f"  - {col} ({dtype}): sample values {sample}")
    columns_text = "\n".join(columns_desc)

    stats_text = str(df.describe(include='all').to_string())

    prompt = f"""You are a data analyst assistant. The user has uploaded a CSV with {len(df)} rows and {len(df.columns)} columns.

Columns:
{columns_text}

Summary statistics:
{stats_text}

User question: {question}

Respond with a JSON object containing:
- "answer": A clear, concise natural-language answer to the question.
- "code": (optional) Python/Pandas code that computes the answer. The DataFrame is available as `df`. Only use pandas and numpy (imported as pd and np). Do NOT use print(). Assign the final result to a variable called `result`.
- "chart": (optional) A Plotly chart specification as a JSON object with "type" (histogram/scatter/bar/line/pie), "title", "x" (column name or list), "y" (column name or list, if applicable). Only include if a visualization would help answer the question.

Respond ONLY with valid JSON. No markdown fences, no explanation outside the JSON."""

    try:
        response = requests.post(
            f"{ollama_url}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
                "options": {"temperature": 0.1, "num_predict": 2048},
            },
            timeout=120,
        )
        response.raise_for_status()
        content = response.json().get("message", {}).get("content", "")
    except requests.exceptions.ConnectionError:
        return {
            "answer": "Cannot connect to Ollama. Make sure it's running at " + ollama_url,
            "error": True,
        }
    except Exception as e:
        return {"answer": f"LLM request failed: {str(e)}", "error": True}

    # Parse LLM response
    parsed = _extract_json(content)
    if not parsed:
        return {"answer": content.strip(), "raw_response": True}

    result = {"answer": parsed.get("answer", content)}

    # Execute generated code if present
    code = parsed.get("code")
    if code:
        result["code"] = code
        exec_result = _safe_exec(code, df)
        if exec_result.get("error"):
            result["exec_error"] = exec_result["error"]
        elif exec_result.get("result") is not None:
            val = exec_result["result"]
            if isinstance(val, pd.DataFrame):
                result["table"] = {
                    "columns": val.columns.tolist(),
                    "rows": val.head(50).values.tolist(),
                }
            elif isinstance(val, pd.Series):
                result["table"] = {
                    "columns": [val.name or "value"],
                    "rows": [[v] for v in val.head(50).tolist()],
                }
            else:
                result["computed"] = str(val)

    # Pass through chart spec if provided
    if parsed.get("chart"):
        result["chart"] = parsed["chart"]

    return result


def _extract_json(text):
    """Extract a JSON object from LLM output, handling markdown fences."""
    text = text.strip()
    # Remove markdown code fences
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def _safe_exec(code, df):
    """Execute Pandas code in a restricted namespace.

    WARNING: This sandbox is NOT secure for multi-user or public deployments.
    It uses a blocklist approach which can be bypassed by a determined attacker
    or a sufficiently creative LLM. Only use in local/single-user contexts.
    For production use, run code in a subprocess with seccomp/namespace isolation.
    """
    import numpy as np

    # Block dangerous patterns — strings and regex for whitespace-insensitive matching
    forbidden_strings = [
        'subprocess', 'shutil', 'pathlib', 'importlib',
        '__import__', '__builtins__', '__globals__', '__subclasses__',
        'getattr', 'setattr', 'delattr', 'globals', 'locals',
        'breakpoint', 'compile',
    ]
    forbidden_patterns = [
        r'import\s+os', r'import\s+sys', r'from\s+os', r'from\s+sys',
        r'eval\s*\(', r'exec\s*\(', r'open\s*\(',  r'type\s*\(',
        r'\.to_csv', r'\.to_excel', r'\.to_parquet', r'\.to_json\s*\(',
        r'\.to_file', r'\.save\s*\(', r'\.write\s*\(',
        r'read_csv\s*\(', r'read_excel', r'read_parquet', r'read_json\s*\(',
        r'read_sql', r'read_html', r'read_fwf',
    ]

    for f in forbidden_strings:
        if f in code:
            return {"error": f"Blocked: code contains '{f}'"}
    for pattern in forbidden_patterns:
        if re.search(pattern, code):
            return {"error": f"Blocked: code matches forbidden pattern"}

    namespace = {"df": df.copy(), "pd": pd, "np": np}
    try:
        exec(code, {"__builtins__": {}}, namespace)
        return {"result": namespace.get("result")}
    except Exception:
        return {"error": traceback.format_exc().split('\n')[-2]}


def check_ollama_health(ollama_url):
    """Check if Ollama is reachable."""
    try:
        r = requests.get(f"{ollama_url}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        return {"available": True, "models": models}
    except Exception:
        return {"available": False, "models": []}
