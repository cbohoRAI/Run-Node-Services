"""Shutdown configuration for the enhanced shutdown system."""

SHUTDOWN_CONFIG = {
    "graceful_timeout": 20.0,      # Increased from 15.0 - Overall graceful shutdown timeout
    "emergency_timeout": 90.0,     # Increased from 60.0 - Emergency exit timeout
    "force_kill_timeout": 8.0,     # Increased from 5.0 - Force kill timeout after graceful
    
    "node_process": {
        "discovery_timeout": 10.0,
        "termination_timeout": 10.0,
        "port_release_timeout": 10.0,
    },
    
    "asyncio": {
        "task_cancel_timeout": 10.0,
        "transport_close_timeout": 10.0,
        "loop_cleanup_timeout": 10.0,
    },
    
    "ui": {
        "show_progress": True,
        "progress_update_interval": 0.5,
    },
    
    "phases": {
        "stop_accepting": 1.0,
        "cancel_tasks": 3.0,
        "terminate_node": 15.0,      # Increased from 10.0
        "kill_wrappers": 15.0,       # Increased from 10.0 - This is the problematic phase
        "close_transports": 10.0,
        "cleanup_loop": 10.0
    }
}