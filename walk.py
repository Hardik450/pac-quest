from pathlib import Path

def combine_files_to_md(output_filename="combined_codebase.md"):
    current_dir = Path('.')
    
    # Map file extensions to their Markdown syntax highlighting names
    target_extensions = {
        '.py': 'python',
        '.js': 'javascript',
        '.css': 'css',
        '.html': 'html'
    }
    
    # Directories to ignore so we don't dump massive dependency folders
    ignore_dirs = {'.git', 'node_modules', 'venv', 'env', '__pycache__', '.next', 'dist', 'build'}
    
    # Exclude this script itself and the output file
    ignore_files = {Path(__file__).name, output_filename}

    files_to_process = []
    
    # rglob('*') searches recursively through all subdirectories
    for filepath in current_dir.rglob('*'):
        if not filepath.is_file():
            continue
            
        # Check if the file is in an ignored directory
        if any(part in ignore_dirs for part in filepath.parts):
            continue
            
        # Check if it's the script itself or the output file
        if filepath.name in ignore_files:
            continue
            
        # Check if it has one of our target extensions
        if filepath.suffix in target_extensions:
            files_to_process.append(filepath)

    if not files_to_process:
        print("No matching files (.py, .js, .css, .html) found.")
        return

    # Write to the markdown file
    with open(output_filename, 'w', encoding='utf-8') as md_file:
        md_file.write("# Codebase Directory Dump\n\n")
        
        for filepath in files_to_process:
            # Get the relative path (e.g., 'src/components/style.css' instead of just 'style.css')
            relative_path = filepath.relative_to(current_dir)
            print(f"Appending: {relative_path}")
            
            # File path as a heading
            md_file.write(f"## `{relative_path}`\n\n")
            
            # Get the correct syntax highlighting language
            language = target_extensions[filepath.suffix]
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    code = f.read()
                    md_file.write(f"```{language}\n")
                    md_file.write(code)
                    if not code.endswith('\n'):
                        md_file.write("\n")
                    md_file.write("```\n\n")
            except Exception as e:
                print(f"Failed to read {relative_path}: {e}")
                md_file.write(f"*> Error reading file: {e}*\n\n")

    print(f"\nSuccess! Compiled {len(files_to_process)} files into '{output_filename}'.")

if __name__ == "__main__":
    combine_files_to_md()