"""
Weather Tool - Demo of Plugin Architecture

This tool demonstrates how to add a new tool WITHOUT modifying:
- agent.py
- registry.py
- Any other existing file

Just drop this file in tools/ and it's automatically discovered!
"""

from .base import BaseTool
import structlog

logger = structlog.get_logger()


class WeatherTool(BaseTool):
    """
    Demo tool: Get current weather for a city.
    
    In a real implementation, this would call a weather API.
    For demo purposes, it returns mock data.
    """
    
    def get_name(self) -> str:
        return "get_weather"
    
    def get_description(self) -> str:
        return "Get current weather for a city. Returns temperature and condition."
    
    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name (e.g., 'San Francisco', 'New York')"
                }
            },
            "required": ["city"]
        }
    
    def execute(self, db_conn, city: str) -> dict:
        """
        Get weather for a city (mock implementation).
        
        Args:
            db_conn: Database connection (not used in this demo)
            city: City name
        
        Returns:
            dict: Weather information
        """
        logger.info("weather.requested", city=city)
        
        # Mock weather data (in reality, call a weather API)
        mock_weather = {
            "San Francisco": {"temperature": 65, "condition": "foggy"},
            "New York": {"temperature": 72, "condition": "sunny"},
            "London": {"temperature": 55, "condition": "rainy"},
            "Tokyo": {"temperature": 80, "condition": "humid"},
        }
        
        if city in mock_weather:
            weather = mock_weather[city]
            return {
                "success": True,
                "city": city,
                "temperature": weather["temperature"],
                "condition": weather["condition"],
                "message": f"Weather in {city}: {weather['temperature']}°F, {weather['condition']}"
            }
        else:
            return {
                "success": False,
                "city": city,
                "error": f"Weather data not available for {city}",
                "message": f"Sorry, I don't have weather data for {city} yet."
            }


# Export singleton instance
weather_tool = WeatherTool()
