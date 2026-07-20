"""
Base class for all tools. Defines the contract that all tools must follow.

This enables a plugin-style architecture where adding a new tool = create a file,
no changes to existing code.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTool(ABC):
    """
    Abstract base class for tools.
    
    All tools must inherit from this class and implement:
    - get_name(): Tool name (must match what the LLM will call)
    - get_description(): Human-readable description for the LLM
    - get_parameters(): OpenAI-format parameter schema
    - execute(): Actually run the tool
    """
    
    @abstractmethod
    def get_name(self) -> str:
        """
        Return the tool name.
        
        This must match the function name that the LLM will use to call the tool.
        
        Returns:
            str: Tool name (e.g., "calculate", "query_database")
        """
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """
        Return the tool description for the LLM.
        
        This is what the LLM reads to decide whether to use the tool.
        
        Returns:
            str: Description of what the tool does
        """
        pass
    
    @abstractmethod
    def get_parameters(self) -> Dict[str, Any]:
        """
        Return the parameter schema in OpenAI format.
        
        Returns:
            dict: Parameter schema with "type", "properties", "required" keys
        """
        pass
    
    @abstractmethod
    def execute(self, db_conn, **kwargs) -> Dict[str, Any]:
        """
        Execute the tool with the given arguments.
        
        Args:
            db_conn: Database connection from the pool
            **kwargs: Tool-specific arguments
        
        Returns:
            dict: Result with at least a "success" key
        """
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """
        Generate OpenAI tool schema from the metadata above.
        
        This is used to tell the LLM what tools are available.
        
        Returns:
            dict: OpenAI-format tool schema
        """
        return {
            "type": "function",
            "function": {
                "name": self.get_name(),
                "description": self.get_description(),
                "parameters": self.get_parameters()
            }
        }
