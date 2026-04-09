"""
PandasPlotBench Evaluation Module

Tier 2: Visual correctness scoring using Claude Vision API.
- Screenshots DashML HTML output via Playwright
- Scores both arms' outputs against task descriptions

Usage:
    python3 benchmark/ppbench_evaluate.py
    python3 benchmark/ppbench_evaluate.py --limit 10
    python3 benchmark/ppbench_evaluate.py --dry-run
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── HTML Screenshot via Playwright ───────────────────────────────────────────

def render_html_to_png(html_path: str, output_png: str, timeout: int = 15000) -> bool:
    """Screenshot an HTML file using Playwright headless Chromium.

    Returns True on success, False on failure.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [WARN] playwright not installed. Run: pip install playwright && playwright install chromium")
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 960})
            page.goto(f"file://{html_path}", wait_until="networkidle", timeout=timeout)
            # Wait for Plotly to render
            page.wait_for_timeout(2000)
            page.screenshot(path=output_png, full_page=False)
            browser.close()
        return True
    except Exception as e:
        print(f"  [WARN] Playwright screenshot failed: {e}")
        return False


def encode_image_base64(image_path: str) -> Optional[str]:
    """Read an image file and return base64 string."""
    path = Path(image_path)
    if not path.exists():
        return None
    return base64.standard_b64encode(path.read_bytes()).decode("utf-8")


# ── Claude Vision Judge ──────────────────────────────────────────────────────

VISUAL_JUDGE_PROMPT = """\
You are evaluating a generated data visualization against a task description.

## Task Description
{task_description}

## Style Requirements
{style_description}

## Instructions
Score the visualization on content correctness (0-100):
- Does it use the correct chart type for the task?
- Does it map the right data columns to the right visual channels?
- Does it show the correct aggregation/grouping?
- Does it apply the described styling where feasible?

Do NOT penalize for:
- Different color schemes or themes
- Different fonts or text positioning
- Dashboard-style layout vs plain chart
- Minor axis label formatting differences

## Scoring Guide
- 90-100: Correct chart type, correct data mapping, correct aggregation
- 70-89: Correct chart type and mostly correct data, minor issues
- 50-69: Partially correct (right chart type but wrong columns, or wrong aggregation)
- 30-49: Wrong chart type but related (e.g., bar instead of grouped bar)
- 0-29: Completely wrong or no useful visualization

Respond with a brief explanation (2-3 sentences) then on the LAST line:
[SCORE]: <number>
"""


class VisualJudge:
    """Claude Vision-based visual evaluation scorer."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def _cache_key(self, task_description: str, image_b64: str) -> str:
        content = f"visual_judge::{self.model}::{task_description}::{image_b64[:100]}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def score(
        self,
        task_description: str,
        style_description: str,
        image_path: str,
        cache_dir: Optional[Path] = None,
    ) -> Tuple[int, str]:
        """Score an image against a task description.

        Returns (score: 0-100, explanation: str).
        """
        image_b64 = encode_image_base64(image_path)
        if image_b64 is None:
            return 0, "Image file not found"

        # Determine media type
        ext = Path(image_path).suffix.lower()
        media_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".html": None,  # Can't score HTML directly
        }.get(ext, "image/png")

        if media_type is None:
            return 0, f"Cannot score file type: {ext}"

        # Check cache
        cache_key = self._cache_key(task_description, image_b64)
        if cache_dir:
            cached_path = cache_dir / f"visual_{cache_key}.json"
            if cached_path.exists():
                try:
                    cached = json.loads(cached_path.read_text())
                    return cached["score"], cached["explanation"]
                except (json.JSONDecodeError, KeyError):
                    pass

        # Call Claude Vision
        prompt = VISUAL_JUDGE_PROMPT.format(
            task_description=task_description,
            style_description=style_description,
        )

        client = self._get_client()
        response = client.messages.create(
            model=self.model,
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )

        text = response.content[0].text
        score = self._extract_score(text)
        explanation = text.rsplit("[SCORE]", 1)[0].strip() if "[SCORE]" in text else text

        # Cache the result
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cached_path = cache_dir / f"visual_{cache_key}.json"
            cached_path.write_text(json.dumps({"score": score, "explanation": explanation}))

        return score, explanation

    @staticmethod
    def _extract_score(text: str) -> int:
        """Extract numeric score from [SCORE]: N pattern."""
        import re
        match = re.search(r"\[SCORE\]\s*:\s*(\d+)", text)
        if match:
            return min(100, max(0, int(match.group(1))))
        # Fallback: look for any number on the last line
        lines = text.strip().split("\n")
        if lines:
            nums = re.findall(r"\b(\d{1,3})\b", lines[-1])
            if nums:
                return min(100, max(0, int(nums[-1])))
        return 0


# ── Main Evaluation Pipeline ────────────────────────────────────────────────

def run_visual_evaluation(
    results_dir: Path,
    cache_dir: Path,
    model: str = "claude-sonnet-4-20250514",
    limit: Optional[int] = None,
    dry_run: bool = False,
):
    """Run visual evaluation on benchmark results."""
    judge = VisualJudge(model=model)

    # Load results from both arms
    scores_path = results_dir / "visual_scores.jsonl"
    scored_ids = set()
    if scores_path.exists():
        with open(scores_path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    scored_ids.add((r["task_id"], r["arm"]))
                except (json.JSONDecodeError, KeyError):
                    continue
        print(f"Resuming: {len(scored_ids)} scores already computed")

    arms_to_score = []
    for arm in ["dashml", "plotly"]:
        results_file = results_dir / f"results_{arm}.jsonl"
        if not results_file.exists():
            print(f"No results for {arm} arm, skipping")
            continue

        with open(results_file) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    if r.get("compile_ok") and r.get("output_path"):
                        arms_to_score.append((arm, r))
                except (json.JSONDecodeError, KeyError):
                    continue

    print(f"Found {len(arms_to_score)} valid outputs to score")
    if limit:
        arms_to_score = arms_to_score[:limit]

    if dry_run:
        # ~500 input tokens per image + prompt, ~100 output
        est_cost = len(arms_to_score) * (500 / 1e6 * 3 + 100 / 1e6 * 15)
        print(f"\n--- DRY RUN ---")
        print(f"  Outputs to score: {len(arms_to_score)}")
        print(f"  Est. cost (Claude Sonnet Vision): ${est_cost:.2f}")
        return

    scores_file = open(scores_path, "a")
    stats = {"total": 0, "score_sum": 0}

    try:
        for arm, result in arms_to_score:
            task_id = result["task_id"]
            if (task_id, arm) in scored_ids:
                continue

            output_path = result["output_path"]
            task_desc = result.get("description", "")

            # For DashML HTML outputs, screenshot first
            if arm == "dashml" and output_path.endswith(".html"):
                png_path = str(Path(output_path).with_suffix(".png"))
                success = render_html_to_png(output_path, png_path)
                if not success:
                    score_entry = {
                        "task_id": task_id,
                        "arm": arm,
                        "score": 0,
                        "explanation": "Failed to screenshot HTML",
                        "screenshot_failed": True,
                    }
                    scores_file.write(json.dumps(score_entry) + "\n")
                    scores_file.flush()
                    continue
                image_to_score = png_path
            else:
                image_to_score = output_path

            # Score
            score, explanation = judge.score(
                task_description=task_desc,
                style_description="",  # Style already in description
                image_path=image_to_score,
                cache_dir=cache_dir,
            )

            stats["total"] += 1
            stats["score_sum"] += score

            score_entry = {
                "task_id": task_id,
                "arm": arm,
                "score": score,
                "explanation": explanation[:300],
            }
            scores_file.write(json.dumps(score_entry) + "\n")
            scores_file.flush()

            n = stats["total"]
            if n % 5 == 0 or n <= 3:
                avg = stats["score_sum"] / n if n else 0
                print(f"  [{task_id:>4d}] {arm:8s} score={score:>3d} | avg={avg:.1f}")

    finally:
        scores_file.close()

    n = stats["total"]
    if n > 0:
        print(f"\n--- VISUAL EVALUATION SUMMARY ---")
        print(f"  Scored: {n}")
        print(f"  Average score: {stats['score_sum']/n:.1f}")


def main():
    parser = argparse.ArgumentParser(
        description="PandasPlotBench Visual Evaluation"
    )
    parser.add_argument(
        "--results", default="benchmark/ppbench_results",
        help="Results directory",
    )
    parser.add_argument(
        "--model", default="claude-sonnet-4-20250514",
        help="Vision model for scoring",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit to first N outputs",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Estimate cost without making API calls",
    )
    args = parser.parse_args()

    results_dir = Path(args.results)
    cache_dir = Path("benchmark/cache")

    run_visual_evaluation(
        results_dir=results_dir,
        cache_dir=cache_dir,
        model=args.model,
        limit=args.limit,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
