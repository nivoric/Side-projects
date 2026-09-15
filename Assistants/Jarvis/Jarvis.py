"""Raw, local Jarvis prototype.

Run with ``python jarvis.py`` for the interactive assistant, or pass a single
command to test it from a shell: ``python jarvis.py "what time is it"``.
"""

from __future__ import annotations

import ast
import datetime as dt
import operator
import os
import platform
import re
import subprocess
import sys
import webbrowser
from pathlib import Path


NOTES_FILE = Path(__file__).with_name("jarvis_notes.txt")
JARVIS_NAME = os.getenv("JARVIS_NAME", "Zido")

_OPERATORS = {
	ast.Add: operator.add,
	ast.Sub: operator.sub,
	ast.Mult: operator.mul,
	ast.Div: operator.truediv,
	ast.FloorDiv: operator.floordiv,
	ast.Mod: operator.mod,
	ast.Pow: operator.pow,
	ast.USub: operator.neg,
	ast.UAdd: operator.pos,
}


def safe_calculate(expression: str) -> int | float:
	"""Evaluate basic arithmetic without exposing Python execution."""
	tree = ast.parse(expression, mode="eval")

	def evaluate(node: ast.AST) -> int | float:
		if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
			return node.value
		if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
			return _OPERATORS[type(node.op)](evaluate(node.operand))
		if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
			left = evaluate(node.left)
			right = evaluate(node.right)
			if abs(right) > 1_000_000 or abs(left) > 1_000_000:
				raise ValueError("numbers are limited to one million")
			return _OPERATORS[type(node.op)](left, right)
		raise ValueError("only basic arithmetic is supported")

	result = evaluate(tree.body)
	if abs(result) > 1_000_000_000:
		raise ValueError("result is too large")
	return result


def _save_note(note: str) -> str:
	with NOTES_FILE.open("a", encoding="utf-8") as notes:
		timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
		notes.write(f"[{timestamp}] {note}\n")
	return "Noted."


def _read_notes() -> str:
	if not NOTES_FILE.exists():
		return "You have no notes yet."
	notes = NOTES_FILE.read_text(encoding="utf-8").strip()
	return notes or "You have no notes yet."


def _create_obsidian_note(note_request: str) -> str:
	vault_setting = os.getenv("OBSIDIAN_VAULT")
	if not vault_setting:
		return "Set the OBSIDIAN_VAULT environment variable to your vault folder first."

	vault = Path(vault_setting).expanduser()
	if not vault.is_dir():
		return f"I could not find the Obsidian vault at {vault}."

	title, separator, content = note_request.partition("|")
	title = title.strip()
	content = content.strip() if separator else ""
	if not title:
		return "Tell me the Obsidian note title."
	if title in {".", ".."} or any(character in title for character in '/\\'):
		return "Use a note title without path separators."

	note_path = vault / f"{title}.md"
	if note_path.exists():
		return f"An Obsidian note named '{title}' already exists."
	note_path.write_text(f"# {title}\n\n{content}\n", encoding="utf-8")
	return f"Created the Obsidian note '{title}'."


def _open_target(target: str) -> str:
	target = target.strip()
	if not target:
		return "Tell me what to open."
	url = target if re.match(r"^https?://", target) else f"https://www.google.com/search?q={target.replace(' ', '+')}"
	webbrowser.open(url)
	return f"Opening {target}."


def _run_system_command(command: str) -> str:
	completed = subprocess.run(
		command,
		shell=True,
		capture_output=True,
		text=True,
		timeout=10,
		cwd=Path.home(),
	)
	output = (completed.stdout or completed.stderr).strip()
	return output[-4000:] if output else f"Command finished with exit code {completed.returncode}."


def handle_command(command: str) -> tuple[str, bool]:
	"""Handle one command and return (response, should_exit)."""
	original = command.strip()
	normalized = original.lower()

	if not original:
		return "Say something, or type 'help'.", False
	if normalized in {"quit", "exit", "goodbye", "shutdown"}:
		return "Shutting down. Good night.", True
	if normalized in {"help", "commands", "what can you do"}:
		return (
			"Commands: whoami, time, date, system info, calculate 2 + 2, "
			"remember <note>, read notes, obsidian note <title> | <content>, "
			"open <site or search>, run <shell command>, quit.",
			False,
		)
	if normalized in {"whoami", "who am i", "my name"}:
		return f"Hello, {JARVIS_NAME}. It is good to see you.", False
	if normalized in {"time", "what time is it", "tell me the time"}:
		return dt.datetime.now().strftime("It is %H:%M."), False
	if normalized in {"date", "what is the date", "today"}:
		return dt.datetime.now().strftime("Today is %A, %B %d, %Y."), False
	if normalized in {"system info", "system", "status"}:
		return f"{platform.system()} {platform.release()} on {platform.machine()}.", False
	if normalized.startswith(("calculate ", "calc ", "math ")):
		expression = re.sub(r"^(calculate|calc|math)\s+", "", original, flags=re.IGNORECASE)
		try:
			return f"{expression} = {safe_calculate(expression)}", False
		except (SyntaxError, ValueError, TypeError, ZeroDivisionError) as error:
			return f"I could not calculate that: {error}.", False
	if normalized.startswith(("remember ", "note ")):
		note = re.sub(r"^(remember|note)\s+", "", original, flags=re.IGNORECASE)
		return _save_note(note), False
	if normalized in {"read notes", "show notes", "notes"}:
		return _read_notes(), False
	if normalized.startswith(("obsidian note ", "create obsidian note ")):
		request = re.sub(r"^(?:create )?obsidian note\s+", "", original, flags=re.IGNORECASE)
		try:
			return _create_obsidian_note(request), False
		except OSError as error:
			return f"I could not create that Obsidian note: {error}.", False
	if normalized.startswith("open "):
		return _open_target(original[5:]), False
	if normalized.startswith("run "):
		try:
			return _run_system_command(original[4:]), False
		except (OSError, subprocess.SubprocessError) as error:
			return f"That command failed: {error}.", False
	return f"I do not know how to handle '{original}'. Type 'help' for commands.", False


def main() -> None:
	print("JARVIS // raw prototype")
	print("Online. Type 'help' for commands, or 'quit' to exit.")
	if len(sys.argv) > 1:
		response, _ = handle_command(" ".join(sys.argv[1:]))
		print(response)
		return
	while True:
		try:
			command = input("\nYou: ")
		except (EOFError, KeyboardInterrupt):
			print("\nShutting down.")
			break
		response, should_exit = handle_command(command)
		print(f"Jarvis: {response}")
		if should_exit:
			break


if __name__ == "__main__":
	main()
