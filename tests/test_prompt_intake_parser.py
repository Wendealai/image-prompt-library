import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARSER_PATH = ROOT / "frontend" / "src" / "utils" / "promptIntake.ts"

NODE_RUNNER = r"""
const fs = require('node:fs');
const ts = require('typescript');
const path = process.argv[1];
const input = process.argv[2];
const source = fs.readFileSync(path, 'utf8');
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }
}).outputText;
const moduleRef = { exports: {} };
new Function('module', 'exports', 'require', transpiled)(moduleRef, moduleRef.exports, require);
const result = moduleRef.exports.parsePromptIntake(input);
process.stdout.write(JSON.stringify(result));
"""


def parse_intake(text: str):
    result = subprocess.run(
        ["node", "--input-type=commonjs", "-e", NODE_RUNNER, str(PARSER_PATH), text],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_prompt_intake_parser_extracts_labeled_fields():
    parsed = parse_intake(
        """Title: Glass Teahouse Hero
Collection: Product commercial
Tags: glass, mist, #cinematic
Source URL: https://example.test/case-study
Model: GPT Image
Author: Edward

English Prompt:
A dreamy glass teahouse hero shot with soft morning mist and reflective highlights.

Simplified Chinese Prompt:
梦幻玻璃茶室主视觉，带有晨雾与高光反射。

Notes:
Homepage launch visual.
""",
    )

    assert parsed == {
        "title": "Glass Teahouse Hero",
        "model": "GPT Image",
        "author": "Edward",
        "sourceUrl": "https://example.test/case-study",
        "cluster": "Product commercial",
        "tags": ["glass", "mist", "cinematic"],
        "englishPrompt": "A dreamy glass teahouse hero shot with soft morning mist and reflective highlights.",
        "simplifiedChinesePrompt": "梦幻玻璃茶室主视觉，带有晨雾与高光反射。",
        "notes": "Homepage launch visual.",
    }


def test_prompt_intake_parser_supports_heading_fallbacks_and_hashtags():
    parsed = parse_intake(
        """Aurora perfume still life
https://example.test/aurora
#beauty #still-life

## Prompt
Studio still life of an aurora perfume bottle with prismatic reflections and soft gradients.
""",
    )

    assert parsed == {
        "title": "Aurora perfume still life",
        "sourceUrl": "https://example.test/aurora",
        "tags": ["beauty", "still-life"],
        "englishPrompt": "Studio still life of an aurora perfume bottle with prismatic reflections and soft gradients.",
    }
