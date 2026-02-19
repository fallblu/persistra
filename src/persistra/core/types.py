"""
src/persistra/core/types.py

Formal type descriptor system for socket compatibility checking.
Replaces the simple issubclass check with a richer type model that
supports concrete types (with optional dtype/shape constraints),
union types, and a wildcard any type.
"""
from __future__ import annotations

from typing import Optional, Type


class SocketType:
    """Base class for all socket type descriptors."""

    def accepts(self, other: SocketType) -> bool:
        """Return True if data described by *other* can flow into a socket of this type."""
        raise NotImplementedError


class ConcreteType(SocketType):
    """Exact DataWrapper subclass, optionally with shape/dtype constraints."""

    def __init__(
        self,
        wrapper_cls: Type,
        *,
        dtype: Optional[str] = None,
        shape: Optional[tuple] = None,
    ):
        self.wrapper_cls = wrapper_cls
        self.dtype = dtype      # e.g., "float64"
        self.shape = shape      # e.g., (None, 3) — None means "any size on that axis"

    def accepts(self, other: SocketType) -> bool:
        if isinstance(other, ConcreteType):
            if not issubclass(other.wrapper_cls, self.wrapper_cls):
                return False
            if self.dtype and other.dtype and self.dtype != other.dtype:
                return False
            if self.shape and other.shape:
                if len(self.shape) != len(other.shape):
                    return False
                for s_dim, o_dim in zip(self.shape, other.shape):
                    if s_dim is not None and s_dim != o_dim:
                        return False
            return True
        if isinstance(other, UnionType):
            return any(self.accepts(t) for t in other.types)
        if isinstance(other, AnyType):
            return True
        return False

    def __repr__(self) -> str:
        parts = [self.wrapper_cls.__name__]
        if self.dtype:
            parts.append(f"dtype={self.dtype}")
        if self.shape:
            parts.append(f"shape={self.shape}")
        return f"ConcreteType({', '.join(parts)})"


class UnionType(SocketType):
    """Socket accepts any of several concrete types."""

    def __init__(self, *types: SocketType):
        self.types = types

    def accepts(self, other: SocketType) -> bool:
        return any(t.accepts(other) for t in self.types)

    def __repr__(self) -> str:
        return f"UnionType({', '.join(repr(t) for t in self.types)})"


class AnyType(SocketType):
    """Socket accepts any DataWrapper."""

    def accepts(self, other: SocketType) -> bool:
        return True

    def __repr__(self) -> str:
        return "AnyType()"
