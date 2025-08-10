# app.py
# AI Code Generator (Gradio) — Markdown viewers to avoid language support issues

import os
import tempfile
from textwrap import dedent
from datetime import datetime

import gradio as gr
from dotenv import load_dotenv
from openai import OpenAI

# ----------------------------
# Setup
# ----------------------------
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY. Create a .env file or set the env var.")

client = OpenAI(api_key=API_KEY)

# ----------------------------
# Language Profiles
# ----------------------------
LANG_PROFILES = {
    "python": {
        "fence_lang": "python",
        "file_ext": "py",
        "test_framework": "pytest",
        "test_hint": "Use pytest. Put tests in a single test file with clear, runnable test functions.",
        "run_hint": "Run the program with: python main.py\nRun tests with: pytest -q",
        "doc_hint": "Include setup, run instructions, and examples for CLI usage if relevant.",
        "example_filename": "main.py",
        "example_test_filename": "test_main.py",
        "readme_name": "README.md",
    },
    "java": {
        "fence_lang": "java",
        "file_ext": "java",
        "test_framework": "JUnit 5",
        "test_hint": "Use JUnit 5. Provide a single test class with multiple test methods.",
        "run_hint": "If using Maven: mvn -q test\nCompile/run manually with javac/java as applicable.",
        "doc_hint": "Explain how to compile and run via Maven or javac. Include classpath notes.",
        "example_filename": "TinyUrl.java",
        "example_test_filename": "TinyUrlTest.java",
        "readme_name": "README.md",
    },
    "javascript": {
        "fence_lang": "javascript",
        "file_ext": "js",
        "test_framework": "vitest",
        "test_hint": "Use vitest. Export functions for testability and include a few focused tests.",
        "run_hint": "Run with: node main.js\nRun tests with: npx vitest run",
        "doc_hint": "Document Node version, install instructions, and test commands.",
        "example_filename": "main.js",
        "example_test_filename": "main.test.js",
        "readme_name": "README.md",
    },
}

# ----------------------------
# Prompt Builders
# ----------------------------
def code_prompt(requirements: str, language: str) -> str:
    p = LANG_PROFILES[language]
    return dedent(f"""
    You are a senior {language} engineer. Generate a single, self-contained source file.

    Requirements:
    {requirements.strip()}

    Constraints:
    - Use idiomatic, minimal, production-quality {language}.
    - Include clear function/class names.
    - Avoid placeholders and pseudo-code.
    - If configuration is needed, include sane defaults in code.
    - Provide only the code for one file. Do NOT include explanations.
    - Prefer a filename like: {p['example_filename']}

    Output strictly as a fenced code block with the correct language.
    """)

def tests_prompt(code: str, language: str) -> str:
    p = LANG_PROFILES[language]
    return dedent(f"""
    You are a senior {language} engineer. Write unit tests for the code below.

    Original code:
    ```
    {code}
    ```

    Testing requirements:
    - Framework: {p['test_framework']}.
    - {p['test_hint']}
    - Cover happy paths and at least one edge case.
    - Provide only ONE test file named like {p['example_test_filename']}.
    - Output strictly as a fenced code block with the correct language or 'text' if needed.
    """)

def docs_prompt(code: str, language: str) -> str:
    p = LANG_PROFILES[language]
    return dedent(f"""
    You are a technical writer. Produce a concise README.md for this project.

    Code to document:
    ```
    {code}
    ```

    Include:
    - Project overview and core features
    - Quick start
    - How to run the program
    - How to run tests ({p['test_framework']})
    - Notes / limitations
    - Example usage

    Hints:
    - {p['run_hint']}
    - {p['doc_hint']}

    Output strictly as a fenced code block marked 'markdown' with a valid README.md.
    """)

# ----------------------------
# OpenAI helper
# ----------------------------
def llm_fenced_block(prompt: str, lang_hint: str) -> str:
    """
    Calls OpenAI and extracts the first fenced code block content.
    Falls back to raw content if no fence is found.
    """
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {"role": "system", "content": "You are precise and only return what is asked."},
            {"role": "user", "content": prompt}
        ],
    )
    content = resp.choices[0].message.content or ""
    fence = f"```{lang_hint}"
    if fence in content:
        try:
            snippet = content.split(fence, 1)[1]
            snippet = snippet.split("```", 1)[0]
            return snippet.strip()
        except Exception:
            return content.strip()
    if "```" in content:
        try:
            snippet = content.split("```", 1)[1]
            snippet = snippet.split("```", 1)[0]
            return snippet.strip()
        except Exception:
            return content.strip()
    return content.strip()

def wrap_as_markdown_code(snippet: str, fence_lang: str) -> str:
    """Wrap plain code into a fenced block for Markdown rendering."""
    return f"```{fence_lang}\n{snippet.strip()}\n```"

# ----------------------------
# File helpers
# ----------------------------
def write_temp_file(text: str, filename: str) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    base, ext = os.path.splitext(filename)
    safe_name = f"{base}-{ts}{ext}" if ext else f"{filename}-{ts}.txt"
    path = os.path.join(tempfile.gettempdir(), safe_name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path

# ----------------------------
# Button callbacks
# ----------------------------
def on_generate_code(requirements: str, language: str):
    if not requirements or not language:
        return gr.update(value=""), None, gr.update(visible=True, value="Please enter requirements and choose a language.")
    if language not in LANG_PROFILES:
        return gr.update(value=""), None, gr.update(visible=True, value=f"Unsupported language: {language}")

    prompt = code_prompt(requirements, language)
    raw_code = llm_fenced_block(prompt, LANG_PROFILES[language]["fence_lang"])
    md_view = wrap_as_markdown_code(raw_code, LANG_PROFILES[language]["fence_lang"])
    filename = LANG_PROFILES[language]["example_filename"]
    file_path = write_temp_file(raw_code, filename)
    return md_view, file_path, gr.update(visible=False, value="")

def on_generate_tests(current_code_md: str, language: str):
    if not current_code_md or not language:
        return gr.update(value=""), None, gr.update(visible=True, value="Generate code first (or paste code) and choose a language.")
    # Extract inner code from fenced markdown viewer
    code = current_code_md.strip()
    if code.startswith("```"):
        try:
            code = code.split("\n", 1)[1]           # drop first line ```
            code = code.rsplit("```", 1)[0].strip() # drop trailing ```
        except Exception:
            pass

    prompt = tests_prompt(code, language)
    raw_tests = llm_fenced_block(prompt, LANG_PROFILES[language]["fence_lang"])
    md_view = wrap_as_markdown_code(raw_tests, LANG_PROFILES[language]["fence_lang"])
    filename = LANG_PROFILES[language]["example_test_filename"]
    file_path = write_temp_file(raw_tests, filename)
    return md_view, file_path, gr.update(visible=False, value="")

def on_generate_docs(current_code_md: str, language: str):
    if not current_code_md or not language:
        return gr.update(value=""), None, gr.update(visible=True, value="Generate code first (or paste code) and choose a language.")
    # Extract inner code from fenced markdown viewer
    code = current_code_md.strip()
    if code.startswith("```"):
        try:
            code = code.split("\n", 1)[1]
            code = code.rsplit("```", 1)[0].strip()
        except Exception:
            pass

    prompt = docs_prompt(code, language)
    raw_md = llm_fenced_block(prompt, "markdown")
    md_view = wrap_as_markdown_code(raw_md, "markdown")
    filename = LANG_PROFILES[language]["readme_name"]
    file_path = write_temp_file(raw_md, filename)
    return md_view, file_path, gr.update(visible=False, value="")

# ----------------------------
# UI
# ----------------------------
with gr.Blocks(title="AI Code Generator", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🚀 AI Code Generator")
    gr.Markdown("Generate high-quality code, unit tests, and documentation with AI.")

    with gr.Row():
        requirements = gr.Textbox(
            label="Enter Code Requirements",
            placeholder="e.g., create a TinyURL class with basic functionality",
            lines=8
        )
        language = gr.Dropdown(
            label="Select Programming Language",
            choices=list(LANG_PROFILES.keys()),
            value="java",
        )

    with gr.Row():
        btn_gen_code = gr.Button("🚀 Generate Code", variant="primary")
        btn_gen_tests = gr.Button("✍️ Generate Unit Tests")
        btn_gen_docs = gr.Button("📚 Generate Documentation")

    with gr.Tab("Generated Code"):
        code_view = gr.Markdown("")  # show fenced code blocks
        dl_code = gr.DownloadButton(label="💾 Download Code File", value=None)
    with gr.Tab("Unit Tests"):
        tests_view = gr.Markdown("")
        dl_tests = gr.DownloadButton(label="💾 Download Tests File", value=None)
    with gr.Tab("Documentation"):
        docs_view = gr.Markdown("")
        dl_docs = gr.DownloadButton(label="💾 Download README.md", value=None)

    alert = gr.Markdown(visible=False)

    btn_gen_code.click(
        fn=on_generate_code,
        inputs=[requirements, language],
        outputs=[code_view, dl_code, alert],
    )
    btn_gen_tests.click(
        fn=on_generate_tests,
        inputs=[code_view, language],
        outputs=[tests_view, dl_tests, alert],
    )
    btn_gen_docs.click(
        fn=on_generate_docs,
        inputs=[code_view, language],
        outputs=[docs_view, dl_docs, alert],
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)
