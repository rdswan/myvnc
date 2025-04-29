#!/usr/bin/env python3
"""
Script to add SPDX license headers to all Python files in the myvnc project.
"""

import os
import sys
import re

# SPDX header to add
SPDX_HEADER = """# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
"""

def add_spdx_header(file_path):
    """Add SPDX header to a Python file if it doesn't already have it."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Check if the file already has SPDX headers
    if "SPDX-FileCopyrightText" in content or "SPDX-License-Identifier" in content:
        print(f"Skipping {file_path} - already has SPDX headers")
        return False
    
    # Handle shebang line if present
    if content.startswith('#!'):
        # Find the end of the shebang line
        shebang_end = content.find('\n')
        if shebang_end == -1:
            shebang_end = len(content)
        
        # Insert the header after the shebang line
        new_content = content[:shebang_end+1] + "\n" + SPDX_HEADER + content[shebang_end+1:]
    else:
        # Add header to the beginning of the file
        new_content = SPDX_HEADER + content
    
    # Write the updated content back to the file
    with open(file_path, 'w') as f:
        f.write(new_content)
    
    print(f"Added SPDX header to {file_path}")
    return True

def find_python_files(directory):
    """Recursively find all Python files in a directory."""
    python_files = []
    for root, _, files in os.walk(directory):
        # Skip virtual environment directories
        if ".venv" in root or "venv" in root:
            continue
        
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    return python_files

def main():
    """Main function to process all Python files."""
    # Use current directory if no argument is provided
    target_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    
    python_files = find_python_files(target_dir)
    
    print(f"Found {len(python_files)} Python files")
    
    modified_count = 0
    for file_path in python_files:
        if add_spdx_header(file_path):
            modified_count += 1
    
    print(f"Added SPDX headers to {modified_count} files")

if __name__ == "__main__":
    main() 