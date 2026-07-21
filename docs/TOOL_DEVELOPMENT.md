# Tool Development Guide

This guide explains how to create and integrate tools into the c-db agent.

## Overview

The c-db agent uses a plugin-based architecture where tools are automatically discovered and registered. To add a new tool, you simply create a Python file in the `tools/` directory that extends `BaseTool`.

## Creating a Tool

### Basic Tool Structure

```python
from tools.base import BaseTool
import structlog

logger = structlog.get_logger()

class MyTool(BaseTool):
    def get_name(self) -> str:
        return "my_tool"
    
    def get_description(self) -> str:
        return "Does awesome stuff"
    
    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Input parameter"
                }
            },
            "required": ["input"]
        }
    
    def execute(self, db_conn, **kwargs) -> dict:
        try:
            # Your tool logic here
            result = process_input(kwargs.get("input"))
            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            logger.error("my_tool.failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

# Export the tool instance
my_tool = MyTool()
```

### Required Methods

Every tool must implement the following methods:

#### `get_name() -> str`
Returns the tool's identifier. This must match what the LLM will call the tool.

**Example:** `"calculate"`, `"query_database"`, `"my_tool"`

#### `get_description() -> str`
Returns a human-readable description that the LLM uses to understand when to use the tool.

**Example:** `"Evaluate a math expression and store the result in the database"`

#### `get_parameters() -> dict`
Returns the parameter schema in OpenAI function format. This defines what parameters the tool accepts.

**Format:**
```python
{
    "type": "object",
    "properties": {
        "param1": {
            "type": "string",
            "description": "Description of param1"
        },
        "param2": {
            "type": "integer",
            "description": "Description of param2"
        }
    },
    "required": ["param1"]
}
```

#### `execute(db_conn, **kwargs) -> dict`
Executes the tool logic.

**Parameters:**
- `db_conn`: Database connection from the connection pool (can be `None` if database is unavailable)
- `**kwargs`: Tool-specific parameters from the LLM

**Returns:**
```python
{
    "success": True/False,
    "result": "output data",  # optional
    "error": "error message"  # required if success=False
}
```

## Database Integration

### Simple Table Creation

If your tool needs database tables, implement a `register_schema()` function:

```python
def register_schema():
    from infrastructure.schema_manager import schema_manager
    
    create_sql = """
        CREATE TABLE IF NOT EXISTS my_data (
            id SERIAL PRIMARY KEY,
            input TEXT NOT NULL,
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """
    
    schema_manager.register_table("my_tool", create_sql)
```

### Advanced Migrations

For complex schema changes, use the migration system:

```python
from infrastructure.schema_manager import schema_manager, Migration

def register_schema():
    # Initial table creation
    migration1 = Migration(
        version="001",
        description="Create initial my_data table",
        up_sql="""
            CREATE TABLE IF NOT EXISTS my_data (
                id SERIAL PRIMARY KEY,
                input TEXT NOT NULL,
                result TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """,
        down_sql="DROP TABLE IF EXISTS my_data;"
    )
    
    # Add a column later
    migration2 = Migration(
        version="002",
        description="Add metadata column to my_data",
        up_sql="ALTER TABLE my_data ADD COLUMN metadata JSONB;",
        down_sql="ALTER TABLE my_data DROP COLUMN metadata;"
    )
    
    schema_manager.register_migration("my_tool", migration1)
    schema_manager.register_migration("my_tool", migration2)
```

## Error Handling

### Database Unavailability

Always handle cases where the database might be unavailable:

```python
def execute(self, db_conn, **kwargs) -> dict:
    if db_conn is None:
        return {
            "success": False,
            "error": "Database unavailable - tool requires database connection"
        }
    
    try:
        # Your logic here
        pass
    except Exception as e:
        logger.error("tool.failed", error=str(e))
        return {
            "success": False,
            "error": str(e)
        }
```

### Graceful Degradation

Provide meaningful error messages that help the LLM understand what went wrong:

```python
def execute(self, db_conn, **kwargs) -> dict:
    try:
        # Tool logic
        pass
    except ValueError as e:
        return {
            "success": False,
            "error": f"Invalid input: {e}"
        }
    except ConnectionError as e:
        return {
            "success": False,
            "error": "External service unavailable"
        }
    except Exception as e:
        logger.error("tool.unexpected_error", error=str(e))
        return {
            "success": False,
            "error": "An unexpected error occurred"
        }
```

## Best Practices

### 1. Use Structured Logging

```python
import structlog

logger = structlog.get_logger()

def execute(self, db_conn, **kwargs) -> dict:
    logger.info("tool.starting", input=kwargs.get("input"))
    try:
        # Logic
        logger.info("tool.success", result=result)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error("tool.failed", error=str(e))
        return {"success": False, "error": str(e)}
```

### 2. Validate Input

```python
def execute(self, db_conn, input: str) -> dict:
    if not input or not input.strip():
        return {
            "success": False,
            "error": "Input cannot be empty"
        }
    
    if len(input) > 1000:
        return {
            "success": False,
            "error": "Input too long (max 1000 characters)"
        }
    
    # Continue with processing
```

### 3. Use Transactions Properly

```python
def execute(self, db_conn, **kwargs) -> dict:
    try:
        with db_conn.cursor() as cur:
            cur.execute("INSERT INTO my_table (col1) VALUES (%s)", (value1,))
            cur.execute("UPDATE other_table SET col2 = %s", (value2,))
        
        db_conn.commit()
        return {"success": True}
    except Exception as e:
        db_conn.rollback()
        logger.error("tool.transaction_failed", error=str(e))
        return {"success": False, "error": str(e)}
```

### 4. Provide Contextual Results

```python
return {
    "success": True,
    "result": processed_data,
    "metadata": {
        "processed_at": datetime.now().isoformat(),
        "items_processed": len(items),
        "processing_time_ms": elapsed_time
    }
}
```

## Tool Registration

Tools are automatically discovered when the agent starts. The system:

1. Scans the `tools/` directory
2. Finds all classes that inherit from `BaseTool`
3. Instantiates them (the singleton instance at module level)
4. Registers them with the tool registry

### Manual Registration (Optional)

If you need to register a tool manually:

```python
from tools.registry import registry

# In your tool file
class MyTool(BaseTool):
    # ... implementation

my_tool = MyTool()

# In agent initialization or tool loading
registry.register(my_tool)
```

## Testing Your Tool

Create test files in the `tests/` directory:

```python
# tests/test_my_tool.py
import pytest
from tools.my_tool import MyTool

@pytest.fixture
def tool():
    return MyTool()

def test_basic_execution(tool, mock_db):
    conn, cursor = mock_db
    result = tool.execute(db_conn=conn, input="test")
    assert result["success"] is True
    assert "result" in result

def test_error_handling(tool, mock_db):
    conn, cursor = mock_db
    result = tool.execute(db_conn=conn, input="")
    assert result["success"] is False
    assert "error" in result
```

## Examples

### Simple Calculator Tool

See `tools/calculator.py` for a complete example of a tool that:
- Evaluates mathematical expressions
- Stores results in the database
- Handles errors gracefully
- Uses restricted eval() for security

### Database Query Tool

See `tools/db_tool.py` for a tool that:
- Executes SQL queries
- Validates SQL for safety
- Handles different query types (SELECT, INSERT, etc.)
- Serializes complex database types

### Email Tools

See `tools/email/` for examples of:
- Multiple related tools in a subdirectory
- Shared utilities in `__init__.py`
- PDF text extraction
- LLM integration for content generation

## Configuration

Tools can access configuration via environment variables:

```python
import os

def execute(self, db_conn, **kwargs) -> dict:
    api_key = os.getenv("MY_TOOL_API_KEY")
    if not api_key:
        return {
            "success": False,
            "error": "MY_TOOL_API_KEY not configured"
        }
    # Continue with processing
```

## Observability

Tools are automatically instrumented with Sentry spans. You can add custom spans:

```python
import sentry_sdk

def execute(self, db_conn, **kwargs) -> dict:
    with sentry_sdk.start_span(op="tool", description="my_tool_processing"):
        # Your logic here
        pass
```

## Troubleshooting

### Tool Not Discovered

- Ensure the tool file is in the `tools/` directory
- Make sure the tool class inherits from `BaseTool`
- Export the tool instance at module level: `my_tool = MyTool()`
- Check that the tool file doesn't start with `_`

### Database Issues

- Implement proper error handling for database unavailability
- Use the schema manager for table creation
- Test with `is_db_available()` before critical operations

### LLM Not Calling Tool

- Check that `get_description()` is clear and specific
- Ensure parameter names and descriptions are informative
- Verify the tool solves a problem the LLM actually encounters

## Advanced Topics

### Tool Dependencies

If your tool depends on other tools, you can call them through the registry:

```python
from tools.registry import registry

def execute(self, db_conn, **kwargs) -> dict:
    # Call another tool
    result = registry.execute("other_tool", {"param": "value"}, db_conn)
    if not result["success"]:
        return {"success": False, "error": "Dependency tool failed"}
    
    # Continue processing
```

### Async Operations

For tools that perform async operations, use appropriate patterns:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

def execute(self, db_conn, **kwargs) -> dict:
    def async_operation():
        # Long-running operation
        pass
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(async_operation)
        result = future.result(timeout=30)
    
    return {"success": True, "result": result}
```

## Support

For questions or issues:
1. Check existing tools in `tools/` for examples
2. Review test files in `tests/` for usage patterns
3. Consult the main README.md for architecture overview