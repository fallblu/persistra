"""
src/persistra/core/io.py

Handles serialization of the Project graph using Pickle.
"""
import pickle
from typing import Any
from persistra.core.project import Project

def save_project(project: Project, filepath: str):
    """
    Saves the entire project state to a binary file.
    """
    try:
        with open(filepath, 'wb') as f:
            pickle.dump(project, f)
        print(f"Project saved to {filepath}")
    except Exception as e:
        print(f"Failed to save project: {e}")
        raise e

def load_project(filepath: str) -> Project:
    """
    Loads a project from a binary file.
    """
    try:
        with open(filepath, 'rb') as f:
            project = pickle.load(f)
        
        if not isinstance(project, Project):
            raise TypeError("Loaded file is not a valid Persistra Project")
            
        print(f"Project loaded from {filepath}")
        return project
    except Exception as e:
        print(f"Failed to load project: {e}")
        raise e
