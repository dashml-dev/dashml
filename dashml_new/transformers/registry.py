"""
Transformer Registry - Discovers and manages transformers
"""
from typing import Dict, Type, List
from .base import Transformer


class TransformerRegistry:
    """
    Registry for discovering and loading DashML transformers.

    Transformers can be registered manually or auto-discovered from the transformers package.
    """

    _transformers: Dict[str, Type[Transformer]] = {}

    @classmethod
    def register(cls, transformer_class: Type[Transformer]) -> None:
        """
        Register a transformer class.

        Args:
            transformer_class: Transformer class (not instance)

        Raises:
            ValueError: If transformer with same name already registered
        """
        # Create temporary instance to get name
        instance = transformer_class()
        name = instance.name

        if name in cls._transformers:
            raise ValueError(f"Transformer '{name}' is already registered")

        cls._transformers[name] = transformer_class

    @classmethod
    def get(cls, name: str) -> Transformer:
        """
        Get a transformer instance by name.

        Args:
            name: Transformer name (e.g., 'streamlit')

        Returns:
            Transformer instance

        Raises:
            ValueError: If transformer not found
        """
        if name not in cls._transformers:
            available = ", ".join(cls.list())
            raise ValueError(
                f"Transformer '{name}' not found. "
                f"Available transformers: {available}"
            )

        return cls._transformers[name]()

    @classmethod
    def list(cls) -> List[str]:
        """
        List all registered transformer names.

        Returns:
            List of transformer names
        """
        return list(cls._transformers.keys())

    @classmethod
    def list_detailed(cls) -> List[Dict[str, str]]:
        """
        List all transformers with details.

        Returns:
            List of dicts with 'name' and 'description' keys
        """
        result = []
        for name, transformer_class in cls._transformers.items():
            instance = transformer_class()
            result.append({
                "name": instance.name,
                "description": instance.description
            })
        return result

    @classmethod
    def clear(cls) -> None:
        """Clear all registered transformers (useful for testing)"""
        cls._transformers.clear()
