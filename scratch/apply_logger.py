import os
import re
from pathlib import Path

def process_file(filepath):
    content = filepath.read_text(encoding='utf-8')
    
    # Skip if already imported
    if 'from orchestrator.vibe_logger import exhaustive_log' not in content:
        # Find the first import and add our import right before it
        import_match = re.search(r'^(?:import|from) ', content, flags=re.MULTILINE)
        if import_match:
            idx = import_match.start()
            content = content[:idx] + 'from orchestrator.vibe_logger import exhaustive_log\n' + content[idx:]
        else:
            content = 'from orchestrator.vibe_logger import exhaustive_log\n' + content
            
    # Add @exhaustive_log to all defs
    # Match: optional whitespace, def keyword
    # Negative lookbehind to ensure we don't double decorate
    lines = content.split('\n')
    new_lines = []
    
    for i, line in enumerate(lines):
        match = re.match(r'^(\s*)def \w+\(', line)
        if match:
            indent = match.group(1)
            # Check if previous line has the decorator
            if i > 0 and '@exhaustive_log' in lines[i-1]:
                new_lines.append(line)
            else:
                new_lines.append(f"{indent}@exhaustive_log")
                new_lines.append(line)
        else:
            new_lines.append(line)
            
    new_content = '\n'.join(new_lines)
    if new_content != content:
        filepath.write_text(new_content, encoding='utf-8')
        print(f"Updated {filepath}")

if __name__ == "__main__":
    base_dir = Path(r"c:\Projects\Vibe_trading")
    for d in ["orchestrator", "india-trade-cli/engine", "india-trade-cli/agent"]:
        target_dir = base_dir / d
        if not target_dir.exists(): continue
        for p in target_dir.glob("*.py"):
            if p.name in ["vibe_logger.py", "__init__.py"]:
                continue
            try:
                process_file(p)
            except Exception as e:
                print(f"Error processing {p}: {e}")
