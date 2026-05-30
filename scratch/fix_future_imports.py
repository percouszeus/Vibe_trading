import os
import re
from pathlib import Path

def fix_file(filepath):
    content = filepath.read_text(encoding='utf-8')
    
    # Check if from __future__ import is present
    future_match = re.search(r'^from\s+__future__\s+import\s+\w+', content, flags=re.MULTILINE)
    if not future_match:
        return
        
    lines = content.split('\n')
    future_lines = []
    other_lines = []
    
    for line in lines:
        if re.match(r'^from\s+__future__\s+import\s+', line):
            future_lines.append(line)
        else:
            other_lines.append(line)
            
    # Reassemble: We need to find the module docstring, if any, and place future_lines right after it.
    # A module docstring is a triple-quoted string at the very beginning of the file (possibly preceded by comments/newlines).
    reconstructed = '\n'.join(other_lines)
    
    # Try to find a module docstring at the beginning
    # Match triple double quotes or triple single quotes at the beginning
    docstring_match = re.match(r'^(\s*(?:#.*?\n\s*)*)(["\']{3}.*?["\']{3})', reconstructed, flags=re.DOTALL)
    
    if docstring_match:
        end_idx = docstring_match.end()
        prefix = reconstructed[:end_idx]
        suffix = reconstructed[end_idx:]
        new_content = prefix + '\n\n' + '\n'.join(future_lines) + suffix
    else:
        # No docstring found, put it at the very top (preserving comments/shebang)
        shebang_match = re.match(r'^(\s*(?:#.*?\n\s*)*)', reconstructed)
        if shebang_match:
            end_idx = shebang_match.end()
            prefix = reconstructed[:end_idx]
            suffix = reconstructed[end_idx:]
            new_content = prefix + '\n'.join(future_lines) + '\n\n' + suffix
        else:
            new_content = '\n'.join(future_lines) + '\n\n' + reconstructed
            
    # Standardize spacing around the future imports and check if it changed
    if new_content != content:
        filepath.write_text(new_content, encoding='utf-8')
        print(f"Fixed __future__ import order in {filepath.relative_to(Path('c:/Projects/Vibe_trading'))}")

if __name__ == "__main__":
    base_dir = Path(r"c:\Projects\Vibe_trading")
    for d in ["orchestrator", "india-trade-cli/engine", "india-trade-cli/agent"]:
        target_dir = base_dir / d
        if not target_dir.exists():
            continue
        for p in target_dir.rglob("*.py"):
            try:
                fix_file(p)
            except Exception as e:
                print(f"Error processing {p}: {e}")
