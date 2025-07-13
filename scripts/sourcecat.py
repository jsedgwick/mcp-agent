#!/usr/bin/env python3
"""
Enhanced sourcecat utility for mcp-agent-inspector.

This script concatenates source files, prioritizing modified/added files
compared to upstream, while providing brief summaries for unchanged files.
"""

import os
import sys
import subprocess
from pathlib import Path
import argparse
import chardet
from typing import List, Set, Tuple, Dict
import json
import re

# Extended file extensions for mcp-agent-inspector codebase
SOURCE_EXTENSIONS = {
    '.py', '.pyi',  # Python
    '.ts', '.tsx', '.js', '.jsx',  # TypeScript/JavaScript
    '.md',  # Markdown
    '.yaml', '.yml',  # YAML
    '.json',  # JSON
    '.css', '.scss',  # Styles
    '.html',  # HTML
    '.sh',  # Shell scripts
    'Dockerfile', 'Makefile',  # Special files
}

# Directories to exclude
EXCLUDE_DIRS = {
    '.git', '__pycache__', '.pytest_cache', 'node_modules', 
    'dist', 'build', '.next', 'coverage', '.mypy_cache',
    'venv', 'env', '.env', '.venv', 'virtualenv',
    '.idea', '.vscode', '.DS_Store', '*.egg-info',
    'htmlcov', '.coverage', 'site-packages',
}

# File patterns to exclude
EXCLUDE_PATTERNS = {
    '*.pyc', '*.pyo', '*.so', '*.dylib', '*.dll',
    '*.class', '*.exe', '*.o', '*.a',
    '*.log', '*.lock', '*.tmp', '*.temp',
    '.DS_Store', 'Thumbs.db',
}


def get_git_modified_files(upstream_ref: str = "upstream/main") -> Set[str]:
    """Get list of files modified compared to upstream."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-status', f'{upstream_ref}...HEAD'],
            capture_output=True, text=True, check=True
        )
        
        modified_files = set()
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split('\t')
                if len(parts) >= 2 and parts[0] in ['A', 'M']:  # Added or Modified
                    modified_files.add(parts[1])
        
        return modified_files
    except subprocess.CalledProcessError:
        print(f"Warning: Could not get git diff against {upstream_ref}", file=sys.stderr)
        return set()


def should_include_file(file_path: Path, extensions: Set[str]) -> bool:
    """Check if file should be included based on extension and exclusion rules."""
    # Check if in excluded directory
    for part in file_path.parts:
        if part in EXCLUDE_DIRS:
            return False
    
    # Check excluded patterns
    for pattern in EXCLUDE_PATTERNS:
        if file_path.match(pattern):
            return False
    
    # Check extension or special files
    if file_path.name in SOURCE_EXTENSIONS:
        return True
    
    return file_path.suffix.lower() in extensions


def detect_file_encoding(file_path: Path) -> str:
    """Detect file encoding using chardet."""
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read(10000)  # Read first 10KB
            result = chardet.detect(raw_data)
            return result['encoding'] or 'utf-8'
    except Exception:
        return 'utf-8'


def read_file_content(file_path: Path) -> Tuple[str, bool]:
    """Read file content with encoding detection. Returns (content, success)."""
    encoding = detect_file_encoding(file_path)
    
    for enc in [encoding, 'utf-8', 'latin-1', 'cp1252']:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                return f.read(), True
        except (UnicodeDecodeError, LookupError):
            continue
    
    return f"[Error: Could not decode file with any attempted encoding]", False


def generate_file_summary(file_path: Path, content: str) -> str:
    """Generate a brief summary of a file's content."""
    lines = content.split('\n')
    total_lines = len(lines)
    
    # Detect file type and generate appropriate summary
    if file_path.suffix == '.py':
        # Python file - extract classes and functions
        classes = re.findall(r'^class\s+(\w+)', content, re.MULTILINE)
        functions = re.findall(r'^def\s+(\w+)', content, re.MULTILINE)
        summary_parts = []
        if classes:
            summary_parts.append(f"classes: {', '.join(classes[:5])}")
        if functions:
            summary_parts.append(f"functions: {', '.join(functions[:5])}")
        summary = f"Python module ({total_lines} lines) - {'; '.join(summary_parts)}"
    
    elif file_path.suffix in ['.ts', '.tsx', '.js', '.jsx']:
        # TypeScript/JavaScript - extract exports and components
        exports = re.findall(r'export\s+(?:const|function|class)\s+(\w+)', content)
        components = re.findall(r'(?:function|const)\s+(\w+).*?:\s*(?:React\.)?FC', content)
        summary_parts = []
        if exports:
            summary_parts.append(f"exports: {', '.join(exports[:5])}")
        if components:
            summary_parts.append(f"components: {', '.join(components[:5])}")
        summary = f"{'TypeScript' if file_path.suffix.startswith('.ts') else 'JavaScript'} ({total_lines} lines) - {'; '.join(summary_parts)}"
    
    elif file_path.suffix == '.md':
        # Markdown - extract headers
        headers = re.findall(r'^#+\s+(.+)$', content, re.MULTILINE)
        summary = f"Markdown ({total_lines} lines) - sections: {', '.join(headers[:3])}"
    
    elif file_path.suffix in ['.yaml', '.yml']:
        # YAML - extract top-level keys
        top_keys = re.findall(r'^(\w+):', content, re.MULTILINE)
        unique_keys = list(dict.fromkeys(top_keys))  # Remove duplicates while preserving order
        summary = f"YAML config ({total_lines} lines) - keys: {', '.join(unique_keys[:5])}"
    
    else:
        # Generic summary
        summary = f"{file_path.suffix[1:].upper() if file_path.suffix else 'Text'} file ({total_lines} lines)"
    
    return summary


def collect_files(directories: List[str], extensions: Set[str]) -> List[Path]:
    """Collect all matching files from given directories."""
    all_files = []
    
    for directory in directories:
        path = Path(directory)
        if path.is_file():
            if should_include_file(path, extensions):
                all_files.append(path)
        elif path.is_dir():
            for file_path in path.rglob('*'):
                if file_path.is_file() and should_include_file(file_path, extensions):
                    all_files.append(file_path)
    
    return sorted(all_files)


def concatenate_sources(
    directories: List[str],
    output_file: str = None,
    upstream_ref: str = "upstream/main",
    max_size_mb: float = 10.0,
    include_unchanged: bool = False,
    extensions: Set[str] = None
) -> None:
    """
    Concatenate source files with priority for modified files.
    
    Args:
        directories: List of directories/files to process
        output_file: Output file path (None for stdout)
        upstream_ref: Git reference to compare against
        max_size_mb: Maximum output size in MB
        include_unchanged: Whether to include full content of unchanged files
        extensions: Set of file extensions to include
    """
    if extensions is None:
        extensions = SOURCE_EXTENSIONS
    
    # Get modified files
    modified_files = get_git_modified_files(upstream_ref)
    
    # Collect all files
    all_files = collect_files(directories, extensions)
    
    # Separate modified and unchanged files
    modified_paths = []
    unchanged_paths = []
    
    for file_path in all_files:
        if str(file_path) in modified_files:
            modified_paths.append(file_path)
        else:
            unchanged_paths.append(file_path)
    
    # Prepare output
    output = []
    current_size = 0
    max_size_bytes = max_size_mb * 1024 * 1024
    
    # Header
    output.append("=" * 80)
    output.append(f"Source Concatenation for mcp-agent-inspector")
    output.append(f"Modified files compared to: {upstream_ref}")
    output.append(f"Total files found: {len(all_files)}")
    output.append(f"Modified files: {len(modified_paths)}")
    output.append(f"Unchanged files: {len(unchanged_paths)}")
    output.append("=" * 80)
    output.append("")
    
    # Process modified files first (full content)
    if modified_paths:
        output.append("=" * 80)
        output.append("MODIFIED/ADDED FILES (Full Content)")
        output.append("=" * 80)
        output.append("")
        
        for file_path in modified_paths:
            content, success = read_file_content(file_path)
            
            file_section = []
            file_section.append("-" * 80)
            file_section.append(f"File: {file_path}")
            file_section.append(f"Status: {'Added' if str(file_path) in modified_files else 'Modified'}")
            file_section.append("-" * 80)
            file_section.append(content)
            file_section.append("")
            
            section_text = '\n'.join(file_section)
            section_size = len(section_text.encode('utf-8'))
            
            if current_size + section_size > max_size_bytes:
                output.append(f"\n[WARNING: Output size limit ({max_size_mb}MB) reached. Truncating...]")
                break
            
            output.extend(file_section)
            current_size += section_size
    
    # Process unchanged files (summaries only)
    if unchanged_paths and current_size < max_size_bytes:
        output.append("")
        output.append("=" * 80)
        output.append("UNCHANGED FILES (Summaries)")
        output.append("=" * 80)
        output.append("")
        
        for file_path in unchanged_paths:
            if include_unchanged:
                # Include full content if requested
                content, success = read_file_content(file_path)
                summary = generate_file_summary(file_path, content)
                output.append(f"• {file_path}: {summary}")
                
                if success and include_unchanged:
                    file_section = []
                    file_section.append(f"  Content preview (first 500 chars):")
                    file_section.append(f"  {content[:500]}..." if len(content) > 500 else f"  {content}")
                    file_section.append("")
                    
                    section_text = '\n'.join(file_section)
                    if current_size + len(section_text.encode('utf-8')) < max_size_bytes:
                        output.extend(file_section)
                        current_size += len(section_text.encode('utf-8'))
            else:
                # Just summary
                content, _ = read_file_content(file_path)
                summary = generate_file_summary(file_path, content)
                summary_line = f"• {file_path}: {summary}\n"
                
                if current_size + len(summary_line.encode('utf-8')) < max_size_bytes:
                    output.append(summary_line.rstrip())
                    current_size += len(summary_line.encode('utf-8'))
    
    # Statistics
    output.append("")
    output.append("=" * 80)
    output.append("Summary Statistics")
    output.append("=" * 80)
    output.append(f"Total output size: {current_size / 1024:.1f} KB")
    output.append(f"Files with full content: {len(modified_paths)}")
    output.append(f"Files with summaries only: {len(unchanged_paths)}")
    
    # Write output
    full_output = '\n'.join(output)
    
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(full_output)
        print(f"Output written to: {output_file}")
        print(f"Total size: {current_size / 1024:.1f} KB")
    else:
        print(full_output)


def main():
    parser = argparse.ArgumentParser(
        description="Concatenate source files with priority for modified files compared to upstream."
    )
    parser.add_argument(
        'directories', 
        nargs='*', 
        default=['.'],
        help='Directories or files to process (default: current directory)'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output file (default: stdout)'
    )
    parser.add_argument(
        '-u', '--upstream',
        default='upstream/main',
        help='Upstream git reference to compare against (default: upstream/main)'
    )
    parser.add_argument(
        '-s', '--max-size',
        type=float,
        default=10.0,
        help='Maximum output size in MB (default: 10.0)'
    )
    parser.add_argument(
        '--include-unchanged',
        action='store_true',
        help='Include preview content for unchanged files'
    )
    parser.add_argument(
        '--extensions',
        help='Comma-separated list of file extensions to include (e.g., .py,.ts,.md)'
    )
    
    args = parser.parse_args()
    
    # Parse extensions if provided
    extensions = SOURCE_EXTENSIONS
    if args.extensions:
        extensions = set(ext.strip() for ext in args.extensions.split(','))
        # Ensure extensions start with dot
        extensions = {ext if ext.startswith('.') else f'.{ext}' for ext in extensions}
    
    concatenate_sources(
        directories=args.directories,
        output_file=args.output,
        upstream_ref=args.upstream,
        max_size_mb=args.max_size,
        include_unchanged=args.include_unchanged,
        extensions=extensions
    )


if __name__ == '__main__':
    main()