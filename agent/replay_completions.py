"""Replay a captured prompt against /v1/completions (no chat template, no parsers).

Thesis-B experiment: send the SAME raw prompt to two model sizes and compare,
in the raw generated text, the position of <tool_call> relative to </think>.

The prompt is the exact string vLLM built for a chat turn (stage 0). Get it from
a vLLM log run with VLLM_LOGGING_LEVEL=DEBUG: the line
  "Request chatcmpl-...: prompt: '...'"
Use the 'extract' subcommand to pull it out of a log file; then 'run' to replay.

Examples:
  python3 replay_completions.py extract vllm.log --label asF-9B-F-...-1 --turn 3 -o prompt.txt
  python3 replay_completions.py run prompt.txt --model Qwen3.5-9B -o out_9B.txt
  python3 replay_completions.py run prompt.txt --model Qwen3.5-4B -o out_4B.txt --stop
"""
import argparse, ast, json, re, sys, urllib.request

DEF_URL = "http://localhost:8001/v1"


def analyze(text: str) -> str:
    think = text.find("</think>")
    call = text.find("<tool_call>")
    lines = [f"len={len(text)} chars",
             f"</think>   at {think if think >= 0 else 'MISSING'}",
             f"<tool_call> at {call if call >= 0 else 'MISSING'}"]
    if call >= 0 and (think < 0 or call < think):
        lines.append("VERDICT: tool call INSIDE thinking (</think> missing or after the call)")
    elif call >= 0:
        lines.append("VERDICT: tool call in content (after </think>)")
    elif think >= 0:
        lines.append("VERDICT: thinking closed, no tool call")
    else:
        lines.append("VERDICT: no </think> and no tool call")
    return "\n".join(lines)


def cmd_extract(a):
    pat = re.compile(r"Request (\S+?)(?:-\w+)?: prompt: ('.*'|\".*\"), prompt_token_ids")
    hits = []
    with open(a.log, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = pat.search(line)
            if m and (not a.label or a.label in m.group(1)):
                hits.append(m.group(2))
    if not hits:
        sys.exit("no prompt found (is the log at DEBUG level?)")
    if a.turn < 1 or a.turn > len(hits):
        sys.exit(f"turn {a.turn} out of range: {len(hits)} prompt(s) found")
    prompt = ast.literal_eval(hits[a.turn - 1])
    open(a.out, "w", encoding="utf-8").write(prompt)
    print(f"{len(hits)} prompt(s) found; wrote turn {a.turn} ({len(prompt)} chars) to {a.out}")


def cmd_run(a):
    prompt = open(a.prompt, encoding="utf-8").read()
    body = {"model": a.model, "prompt": prompt, "max_tokens": a.max_tokens,
            "temperature": 0, "skip_special_tokens": False}
    if a.stop:
        body["stop"] = ["</tool_call>"]
        body["include_stop_str_in_output"] = True
    req = urllib.request.Request(a.url.rstrip("/") + "/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=a.timeout) as r:
        out = json.load(r)
    choice = out["choices"][0]
    text = choice["text"]
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
    print(f"model={out.get('model')} finish_reason={choice.get('finish_reason')} "
          f"usage={out.get('usage')}")
    print(analyze(text))
    if a.out:
        print(f"raw text written to {a.out}")
    else:
        print("--- raw text ---"); print(text)


p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = p.add_subparsers(dest="cmd", required=True)
e = sub.add_parser("extract", help="extract a prompt from a DEBUG-level vLLM log")
e.add_argument("log"); e.add_argument("--label", default="", help="substring of the X-Request-Id")
e.add_argument("--turn", type=int, default=1, help="1-based index among the matching prompts")
e.add_argument("-o", "--out", default="prompt.txt")
r = sub.add_parser("run", help="send a prompt file to /v1/completions")
r.add_argument("prompt"); r.add_argument("--model", required=True)
r.add_argument("--url", default=DEF_URL); r.add_argument("--max-tokens", type=int, default=4096)
r.add_argument("--stop", action="store_true", help="use the campaign stop (</tool_call>, included in output)")
r.add_argument("--timeout", type=float, default=600)
r.add_argument("-o", "--out", default="", help="file for the raw generated text")

if __name__ == "__main__":
    a = p.parse_args()
    {"extract": cmd_extract, "run": cmd_run}[a.cmd](a)