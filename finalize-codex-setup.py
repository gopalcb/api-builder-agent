#!/usr/bin/env python3
"""Run from a terminal permitted to create project .codex and .agents directories."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
source = root / 'codex-setup'
target = root / '.codex'
agents = root / '.agents'

# Check protected destinations before moving any existing files.
target.mkdir(exist_ok=True)
agents.mkdir(exist_ok=True)

for directory in (target, agents):
    probe = directory / '.setup-write-check'
    probe.write_text('')
    probe.unlink()

if source.exists():
    conflicts = [p.name for p in source.iterdir() if (target / p.name).exists()]

    if conflicts:
        raise SystemExit(f'Refusing to overwrite existing .codex entries: {conflicts}')

    for entry in source.iterdir():
        shutil.move(str(entry), target / entry.name)

    source.rmdir()

for name in ('docs',):
    old = root / name

    if old.exists():
        if (target / name).exists():
            raise SystemExit(f'Refusing to overwrite .codex/{name}')

        shutil.move(str(old), target / name)

skills = agents / 'skills'
skills.mkdir(exist_ok=True)

for skill in (target / 'skills').iterdir():
    if skill.is_dir():
        link = skills / skill.name

        if not link.exists() and not link.is_symlink():
            link.symlink_to(Path('../../.codex/skills') / skill.name)

# Make copied instructions resolve against this project, not a user's global home.
for base in (target / 'skills', target / 'workflows', target / 'references'):
    for path in base.rglob('*.md'):
        text = path.read_text()
        text = text.replace('$CODEX_HOME/', '.codex/')
        text = text.replace('docs/tasks/', '.codex/docs/tasks/')
        path.write_text(text)

instructions = root / 'AGENTS.md'
text = instructions.read_text().replace('docs/tasks/', '.codex/docs/tasks/')
text = text.split('Fresh Codex setup is staged')[0].rstrip()
text += '\n\nProject configuration, workflows, tools and task documents live in `.codex/`. Skills live in `.codex/skills` and are discoverable through `.agents/skills`. Native memory is enabled in `.codex/config.toml`; restart Codex to load changed configuration.\n'
instructions.write_text(text)
(target / 'AGENTS.md').write_text('Follow the repository root AGENTS.md. Keep plans and brief implementation summaries in .codex/docs/tasks/<task>/. Resolve project tools and workflows from this repository\'s .codex directory.\n')
(target / 'README.md').write_text('# Project Codex setup\n\nConfiguration: config.toml (native memories enabled). Skills: skills/, exposed through ../.agents/skills. Task records: docs/tasks/. Supporting workflows and UI testing tools are local. Restart Codex after installation to load configuration and discover skills. No credentials or source-project session history are included.\n')
record = target / 'docs/tasks/setup/layout-summary.md'
record.parent.mkdir(parents=True, exist_ok=True)
record.write_text('# Layout update\n\nMoved staged setup into .codex and task documents into .codex/docs. Exposed skills through .agents/skills and updated repository instructions. Removed codex-setup. Existing setup summary retains the original test results and limitations; it is historical.\n')

assert not source.exists()
assert (target / 'config.toml').is_file()
assert all((skills / p.name).resolve() == p.resolve() for p in (target / 'skills').iterdir() if p.is_dir())

print('Installed .codex, .codex/docs and .agents/skills; removed codex-setup. Restart Codex to load the setup.')
