"""
Brain Manager - Model-controlled persistent memory.

The brain folder allows the AI to:
1. Write and update its own personality notes
2. Store learned rules and preferences
3. Maintain a scratchpad for multi-turn reasoning
4. Keep track of user context

Structure:
  data/companion_brain/
  ├── system/          (read-only, safety rules)
  │   └── core_rules.md
  ├── memories/        (persistent facts)
  │   ├── user_context.md
  │   └── personality.md
  └── training/        (learning data)
      └── scratchpad.md
"""

import os
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Base path for brain folder
BRAIN_BASE = Path(__file__).parent.parent / "data" / "companion_brain"

# Safety limits
MAX_FILE_SIZE = 100 * 1024  # 100KB per file
MAX_FILES = 50
MAX_TOTAL_SIZE = 5 * 1024 * 1024  # 5MB total

# Protected paths (read-only)
PROTECTED_PATHS = {"system", "system/core_rules.md"}


class BrainManager:
    """
    Manages the AI's persistent brain storage.
    
    Provides safe read/write operations with size limits and path validation.
    """
    
    def __init__(self, base_path: Path = BRAIN_BASE):
        self.base_path = Path(base_path)
        self._ensure_structure()
    
    def _ensure_structure(self):
        """Create brain folder structure if it doesn't exist."""
        for subdir in ["memories", "training", "system"]:
            (self.base_path / subdir).mkdir(parents=True, exist_ok=True)
    
    def _validate_path(self, relative_path: str, write: bool = False) -> Path:
        """
        Validate and resolve a relative path within the brain folder.
        
        Args:
            relative_path: Path relative to brain folder (e.g., "memories/user.md")
            write: If True, check write permissions
            
        Returns:
            Resolved absolute Path
            
        Raises:
            ValueError: If path is invalid or protected
        """
        # Normalize and resolve
        clean_path = relative_path.replace("\\", "/").strip("/")
        full_path = (self.base_path / clean_path).resolve()
        
        # Ensure within brain folder
        try:
            full_path.relative_to(self.base_path.resolve())
        except ValueError:
            raise ValueError(f"Path escapes brain folder: {relative_path}")
        
        # Check protection for writes
        if write:
            for protected in PROTECTED_PATHS:
                if clean_path.startswith(protected):
                    raise ValueError(f"Cannot write to protected path: {relative_path}")
        
        return full_path
    
    def _check_limits(self, content: str, path: Path):
        """Check size limits before writing."""
        content_size = len(content.encode('utf-8'))
        
        # Check individual file size
        if content_size > MAX_FILE_SIZE:
            raise ValueError(f"Content exceeds max file size ({content_size} > {MAX_FILE_SIZE})")
        
        # Check file count
        all_files = list(self.base_path.rglob("*"))
        if len([f for f in all_files if f.is_file()]) >= MAX_FILES and not path.exists():
            raise ValueError(f"Brain folder at max files ({MAX_FILES})")
        
        # Check total size
        current_total = sum(f.stat().st_size for f in all_files if f.is_file())
        if current_total + content_size > MAX_TOTAL_SIZE:
            raise ValueError(f"Brain folder at max size ({MAX_TOTAL_SIZE} bytes)")
    
    def read(self, relative_path: str) -> Optional[str]:
        """
        Read a file from the brain folder.
        
        Args:
            relative_path: Path relative to brain folder
            
        Returns:
            File contents or None if not found
        """
        try:
            path = self._validate_path(relative_path, write=False)
            if path.exists() and path.is_file():
                return path.read_text(encoding='utf-8')
            return None
        except Exception as e:
            logger.error(f"Brain read error: {e}")
            return None
    
    def write(self, relative_path: str, content: str, append: bool = False) -> bool:
        """
        Write content to the brain folder.
        
        Args:
            relative_path: Path relative to brain folder
            content: Text content to write
            append: If True, append to existing content
            
        Returns:
            True if successful
        """
        try:
            path = self._validate_path(relative_path, write=True)
            
            # Prepare content
            if append and path.exists():
                existing = path.read_text(encoding='utf-8')
                content = existing + "\n" + content
            
            # Check limits
            self._check_limits(content, path)
            
            # Ensure parent directory exists
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write with timestamp comment
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            if not append:
                content = f"<!-- Updated: {timestamp} -->\n{content}"
            
            path.write_text(content, encoding='utf-8')
            logger.info(f"Brain write: {relative_path}")
            return True
            
        except Exception as e:
            logger.error(f"Brain write error: {e}")
            return False
    
    def list_files(self, subdir: str = "") -> list[dict]:
        """
        List files in a brain subdirectory.
        
        Args:
            subdir: Subdirectory to list (empty for all)
            
        Returns:
            List of file info dicts
        """
        try:
            if subdir:
                path = self._validate_path(subdir, write=False)
            else:
                path = self.base_path
            
            files = []
            for f in path.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(self.base_path)
                    files.append({
                        "path": str(rel).replace("\\", "/"),
                        "size": f.stat().st_size,
                        "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                    })
            
            return sorted(files, key=lambda x: x["path"])
            
        except Exception as e:
            logger.error(f"Brain list error: {e}")
            return []
    
    def delete(self, relative_path: str) -> bool:
        """
        Delete a file from the brain folder.
        
        Args:
            relative_path: Path to delete
            
        Returns:
            True if successful
        """
        try:
            path = self._validate_path(relative_path, write=True)
            if path.exists() and path.is_file():
                path.unlink()
                logger.info(f"Brain delete: {relative_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Brain delete error: {e}")
            return False
    
    def get_context(self) -> str:
        """
        Get all brain context for injection into system prompt.
        
        Returns:
            Formatted context string
        """
        context_parts = []
        
        # Read key files
        key_files = [
            ("memories/personality.md", "PERSONALITY"),
            ("memories/user_context.md", "USER CONTEXT"),
            ("training/learned_rules.md", "LEARNED RULES"),
        ]
        
        for file_path, label in key_files:
            content = self.read(file_path)
            if content:
                # Strip HTML comments and clean up
                lines = [l for l in content.split("\n") if not l.strip().startswith("<!--")]
                clean = "\n".join(lines).strip()
                if clean:
                    context_parts.append(f"[{label}]\n{clean}")
        
        return "\n\n".join(context_parts)


# Singleton instance
_brain: Optional[BrainManager] = None


def get_brain() -> BrainManager:
    """Get the global BrainManager instance."""
    global _brain
    if _brain is None:
        _brain = BrainManager()
    return _brain


# Convenience functions for tools
def brain_read(path: str) -> str:
    """Read from brain folder."""
    content = get_brain().read(path)
    return content if content else f"File not found: {path}"


def brain_write(path: str, content: str, append: bool = False) -> str:
    """Write to brain folder."""
    if get_brain().write(path, content, append):
        return f"Successfully wrote to {path}"
    return f"Failed to write to {path}"


def brain_list(subdir: str = "") -> str:
    """List brain folder contents."""
    files = get_brain().list_files(subdir)
    if not files:
        return "No files found"
    
    lines = ["Brain folder contents:"]
    for f in files:
        lines.append(f"  {f['path']} ({f['size']} bytes)")
    return "\n".join(lines)


def get_brain_context() -> str:
    """Get brain context for system prompt."""
    return get_brain().get_context()
