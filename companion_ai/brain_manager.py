"""
Brain Manager - Model-controlled persistent memory.

The brain folder allows the AI to:
1. Write and update its own personality notes
2. Store learned rules and preferences
3. Keep track of user context and preferences
4. Maintain bookmarks and browser-related memory

Structure:
    BRAIN/
  ├── system/          (read-only, human-edited)
  │   └── core_rules.md
  ├── memories/        (persistent facts)
  │   ├── preferences.md
  │   ├── user_context.md
  │   └── facts/
  ├── browser/         (browser-related)
  │   ├── bookmarks.md
  │   └── logins.md
  ├── notes/           (scratchpad)
  ├── learned/         (growth)
  │   └── corrections.md
  └── logs/            (session history)
"""

import os
import logging
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

# Base path for brain folder (in project directory for development)
BRAIN_BASE = Path(__file__).parent.parent / "BRAIN"

# Safety limits
MAX_FILE_SIZE = 100 * 1024  # 100KB per file
MAX_FILES = 100
MAX_TOTAL_SIZE = 10 * 1024 * 1024  # 10MB total

# Protected paths (read-only)
PROTECTED_PATHS = {"system", "system/core_rules.md", "system/config.md"}

# File descriptions for the Brain Map
FILE_DESCRIPTIONS = {
    "system/core_rules.md": "Core rules and permissions (READ-ONLY)",
    "memories/preferences.md": "User likes/dislikes (READ/WRITE)",
    "memories/user_context.md": "Who the user is (READ/WRITE)",
    "browser/bookmarks.md": "Saved websites (READ/APPEND)",
    "browser/logins.md": "Login tips/hints (READ/WRITE)",
    "learned/corrections.md": "Past errors to avoid (READ/APPEND)",
    "notes/": "Scratchpad for temporary notes (READ/WRITE)",
}


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
        subdirs = ["system", "memories", "memories/facts", "browser", "notes", "learned", "logs"]
        for subdir in subdirs:
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
    
    def get_file_map(self) -> str:
        """
        Get a map of brain files for injection into system prompt.
        
        This tells the AI what files exist without loading their content.
        
        Returns:
            Formatted file map string
        """
        lines = ["## Brain Map (available files)"]
        
        for file_path, description in FILE_DESCRIPTIONS.items():
            full_path = self.base_path / file_path
            exists = full_path.exists() if not file_path.endswith('/') else full_path.is_dir()
            status = "" if exists else ""
            lines.append(f"- {status} `{file_path}`: {description}")
        
        return "\n".join(lines)
    
    def get_context(self) -> str:
        """
        Get core brain context for injection into system prompt.
        
        Uses TIERED approach:
        - Tier 1 (here): Core rules only (small, always present)
        - Tier 2: Dynamic RAG via memory search (on demand)
        - Tier 3: Heavy processing via local loop (delegated)
        
        Returns:
            Formatted context string (minimal, just essentials)
        """
        context_parts = []
        
        # TIER 1: Core rules only (always loaded, small)
        core_rules = self.read("system/core_rules.md")
        if core_rules:
            # Strip comments
            lines = [l for l in core_rules.split("\n") if not l.strip().startswith("<!--")]
            clean = "\n".join(lines).strip()
            if clean:
                context_parts.append(f"[CORE RULES]\n{clean}")
        
        # Add file map so AI knows what's available
        context_parts.append(self.get_file_map())
        
        return "\n\n".join(context_parts)


# Singleton instance
_brain: Optional[BrainManager] = None
_brains: dict[str, BrainManager] = {}


def _workspace_base_path(workspace_id: str) -> Path:
    workspace = (workspace_id or 'default').strip() or 'default'
    if workspace == 'default':
        return BRAIN_BASE
    return BRAIN_BASE / "workspaces" / workspace


def get_brain(workspace_id: str = 'default') -> BrainManager:
    """Get a BrainManager instance scoped to workspace_id."""
    global _brain
    workspace = (workspace_id or 'default').strip() or 'default'
    if workspace == 'default':
        if _brain is None:
            _brain = BrainManager()
        return _brain

    if workspace not in _brains:
        _brains[workspace] = BrainManager(_workspace_base_path(workspace))
    return _brains[workspace]


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


def get_brain_file_map() -> str:
    """Get brain file map for system prompt."""
    return get_brain().get_file_map()

