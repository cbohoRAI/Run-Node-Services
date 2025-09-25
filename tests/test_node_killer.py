"""Tests for NodeProcessKiller."""
import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock

from src.core.node_killer import NodeProcessKiller


class TestNodeProcessKiller:
    
    @pytest.fixture
    def killer(self):
        """Create a NodeProcessKiller instance."""
        return NodeProcessKiller(graceful_timeout=1.0, force_timeout=1.0)
    
    @patch('src.core.node_killer.find_process_by_port')
    @patch('src.core.node_killer.kill_process_tree')
    @patch('os.kill')
    async def test_kill_node_project_success(self, mock_os_kill, mock_kill_tree, mock_find_port, killer):
        """Test successful killing of a Node.js project."""
        # Mock finding processes on port
        mock_find_port.side_effect = [
            [1234, 1235],  # Initial discovery
            [],            # After termination - no processes remaining
            []             # Port release check
        ]
        
        result = await killer.kill_node_project(
            name="test-project",
            port=3000,
            wrapper_pid=9999,
            known_node_pids={1236}
        )
        
        assert result is True
        
        # Verify SIGTERM was sent to all Node processes
        expected_calls = [
            ((1234, 15),),  # SIGTERM to first process
            ((1235, 15),),  # SIGTERM to second process  
            ((1236, 15),),  # SIGTERM to known PID
        ]
        mock_os_kill.assert_has_calls([Mock(args=args) for args in expected_calls], any_order=True)
        
        # Verify wrapper process was killed
        mock_kill_tree.assert_called_with(9999)
    
    @patch('src.core.node_killer.find_process_by_port')
    @patch('src.core.node_killer.kill_process_tree')
    @patch('os.kill')
    async def test_kill_node_project_force_required(self, mock_os_kill, mock_kill_tree, mock_find_port, killer):
        """Test killing when force termination is required."""
        # Mock processes remaining after graceful termination
        mock_find_port.side_effect = [
            [1234],  # Initial discovery
            [1234],  # Still there after SIGTERM
            []       # Gone after force kill
        ]
        
        result = await killer.kill_node_project(
            name="test-project",
            port=3000,
            wrapper_pid=9999
        )
        
        assert result is False  # Not completely successful due to force kill needed
        
        # Verify SIGTERM was sent first
        mock_os_kill.assert_called_with(1234, 15)
        
        # Verify force kill was called
        mock_kill_tree.assert_any_call(1234)  # Force kill of remaining process
        mock_kill_tree.assert_any_call(9999)  # Wrapper kill
    
    @patch('src.core.node_killer.find_process_by_port')
    async def test_discover_node_processes(self, mock_find_port, killer):
        """Test discovering Node.js processes on a port."""
        mock_find_port.return_value = [1234, 1235]
        
        pids = await killer.discover_node_processes(3000)
        
        assert pids == {1234, 1235}
        mock_find_port.assert_called_once_with(3000)
    
    @patch('src.core.node_killer.find_process_by_port')
    @patch('src.core.node_killer.kill_process_tree')  
    @patch('os.kill')
    async def test_kill_all_on_port(self, mock_os_kill, mock_kill_tree, mock_find_port, killer):
        """Test killing all processes on a specific port."""
        mock_find_port.side_effect = [
            [1234, 1235],  # Initial discovery
            [],            # After termination
            []             # Port release verification
        ]
        
        result = await killer.kill_all_on_port(3000)
        
        assert result is True
        
        # Verify all processes were terminated
        mock_os_kill.assert_any_call(1234, 15)
        mock_os_kill.assert_any_call(1235, 15)
    
    @patch('src.core.node_killer.find_process_by_port')
    async def test_wait_for_port_release_success(self, mock_find_port, killer):
        """Test waiting for port release - success case."""
        mock_find_port.side_effect = [
            [1234],  # First check - still bound
            []       # Second check - released
        ]
        
        result = await killer._wait_for_port_release(3000, timeout=2.0)
        
        assert result is True
    
    @patch('src.core.node_killer.find_process_by_port')
    async def test_wait_for_port_release_timeout(self, mock_find_port, killer):
        """Test waiting for port release - timeout case."""
        mock_find_port.return_value = [1234]  # Always bound
        
        result = await killer._wait_for_port_release(3000, timeout=0.1)
        
        assert result is False
    
    @patch('os.kill')
    async def test_terminate_process_graceful_success(self, mock_os_kill, killer):
        """Test graceful process termination - success."""
        result = await killer._terminate_process_graceful(1234)
        
        assert result is True
        mock_os_kill.assert_called_once_with(1234, 15)  # SIGTERM
    
    @patch('os.kill')
    async def test_terminate_process_graceful_no_such_process(self, mock_os_kill, killer):
        """Test graceful termination when process doesn't exist."""
        mock_os_kill.side_effect = ProcessLookupError("No such process")
        
        result = await killer._terminate_process_graceful(1234)
        
        assert result is True  # Success because process is already gone
    
    @patch('os.kill')
    async def test_terminate_process_graceful_permission_error(self, mock_os_kill, killer):
        """Test graceful termination with permission error."""
        mock_os_kill.side_effect = PermissionError("Permission denied")
        
        result = await killer._terminate_process_graceful(1234)
        
        assert result is False