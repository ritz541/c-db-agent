"""
Tool Registry with Auto-Discovery

This module automatically discovers all tools in the tools/ directory.
Adding a new tool = create a file with a BaseTool subclass, no changes elsewhere.

Usage:
    from tools.registry import registry
    
    # Auto-discover all tools (call once at startup)
    registry.auto_discover()
    
    # Get tool schemas for LLM
    schemas = registry.get_schemas()
    
    # Execute a tool
    result = registry.execute("calculate", {"expression": "15 * 37"}, db_conn)
"""

import importlib
import pkgutil
from pathlib import Path
from typing import Dict, List, Any
import structlog

from .base import BaseTool


logger = structlog.get_logger()


class ToolRegistry:
    """
    Registry for tools with auto-discovery.
    
    Scans the tools/ directory, finds all BaseTool subclasses,
    instantiates them, and makes them available for the agent.
    """
    
    def __init__(self):
        """Initialize an empty registry."""
        self._tools: Dict[str, BaseTool] = {}
        self._schemas: List[Dict[str, Any]] = []
        self._discovered = False
    
    def auto_discover(self):
        """
        Scan tools/ directory and auto-register all tools.
        
        This finds all classes that inherit from BaseTool, instantiates them,
        and registers them. No manual registration needed.
        """
        if self._discovered:
            logger.warning("registry.already_discovered")
            return
        
        tools_dir = Path(__file__).parent
        logger.info("registry.discovering", directory=str(tools_dir))
        
        discovered_count = 0
        
        for importer, modname, ispkg in pkgutil.iter_modules([str(tools_dir)]):
            # Skip private modules and this file itself
            if modname.startswith('_') or modname == 'base' or modname == 'registry':
                continue
            
            try:
                # Import the module
                module_name = f"tools.{modname}"
                module = importlib.import_module(module_name)
                
                # Find all BaseTool subclasses in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    
                    # Check if it's a class, is a subclass of BaseTool, but not BaseTool itself
                    if (isinstance(attr, type) and 
                        issubclass(attr, BaseTool) and 
                        attr != BaseTool):
                        
                        # Instantiate the tool
                        tool_instance = attr()
                        
                        # Register it
                        self.register(tool_instance)
                        discovered_count += 1
                        
            except Exception as e:
                logger.error("registry.module_failed", module=modname, error=str(e))
        
        self._discovered = True
        logger.info("registry.discovery_complete", tools_discovered=discovered_count)
    
    def register(self, tool: BaseTool):
        """
        Register a tool instance.
        
        Args:
            tool: An instance of a BaseTool subclass
        """
        tool_name = tool.get_name()
        
        if tool_name in self._tools:
            logger.warning("registry.tool_overwrite", tool=tool_name)
        
        self._tools[tool_name] = tool
        self._schemas.append(tool.get_schema())
        
        logger.info("registry.tool_registered", tool=tool_name)
    
    def get_schemas(self) -> List[Dict[str, Any]]:
        """
        Return all tool schemas in OpenAI format.
        
        Returns:
            list: List of tool schemas for the LLM
        """
        return self._schemas
    
    def get_tool(self, tool_name: str) -> BaseTool:
        """
        Get a tool instance by name.
        
        Args:
            tool_name: Name of the tool
        
        Returns:
            BaseTool instance or None if not found
        """
        return self._tools.get(tool_name)
    
    def execute(self, tool_name: str, args: Dict[str, Any], db_conn) -> Dict[str, Any]:
        """
        Execute a tool by name.
        
        Args:
            tool_name: Name of the tool to execute
            args: Arguments to pass to the tool
            db_conn: Database connection
        
        Returns:
            dict: Tool execution result
        """
        tool = self._tools.get(tool_name)
        
        if not tool:
            logger.error("registry.tool_not_found", tool=tool_name)
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        try:
            logger.info("registry.tool_executing", tool=tool_name, args=args)
            result = tool.execute(db_conn=db_conn, **args)
            logger.info("registry.tool_completed", tool=tool_name, success=result.get("success", False))
            return result
        except Exception as e:
            logger.error("registry.tool_failed", tool=tool_name, error=str(e))
            return {"success": False, "error": str(e)}
    
    def list_tools(self) -> List[str]:
        """
        List all registered tool names.
        
        Returns:
            list: List of tool names
        """
        return list(self._tools.keys())
    
    def clear(self):
        """Clear all registered tools (mainly for testing)."""
        self._tools.clear()
        self._schemas.clear()
        self._discovered = False


# Global registry instance
# Import this in agent.py and call registry.auto_discover()
registry = ToolRegistry()
