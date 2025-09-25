"""Tests for ResourceRegistry."""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock

from src.core.resource_registry import ResourceRegistry, ProcessInfo


class TestResourceRegistry:
    
    @pytest.fixture
    async def registry(self):
        """Create a ResourceRegistry instance."""
        return ResourceRegistry()
    
    @pytest.fixture
    def mock_process(self):
        """Create a mock subprocess."""
        proc = Mock()
        proc.pid = 1234
        return proc
    
    async def test_register_process(self, registry, mock_process):
        """Test registering a process."""
        await registry.register_process("test-project", mock_process, port=3000, path="/test")
        
        assert "test-project" in registry.processes
        process_info = registry.processes["test-project"]
        assert process_info.wrapper_process is mock_process
        assert process_info.wrapper_pid == 1234
        assert process_info.port == 3000
        assert process_info.path == "/test"
        
        assert "test-project" in registry.ports
        assert registry.ports["test-project"] == 3000
    
    async def test_register_node_pids(self, registry, mock_process):
        """Test registering Node.js PIDs."""
        await registry.register_process("test-project", mock_process, port=3000)
        await registry.register_node_pids("test-project", {5678, 5679})
        
        assert "test-project" in registry.node_pids
        assert registry.node_pids["test-project"] == {5678, 5679}
        
        # Check it's also updated in the process info
        process_info = registry.processes["test-project"]
        assert process_info.node_pids == {5678, 5679}
    
    async def test_register_task(self, registry):
        """Test registering an asyncio task."""
        task = asyncio.create_task(asyncio.sleep(0.1))
        await registry.register_task("test-project", task)
        
        assert "test-project" in registry.tasks
        assert task in registry.tasks["test-project"]
        
        task.cancel()
    
    async def test_get_all_resources(self, registry, mock_process):
        """Test getting all resources for a project."""
        task = asyncio.create_task(asyncio.sleep(0.1))
        
        await registry.register_process("test-project", mock_process, port=3000)
        await registry.register_task("test-project", task)
        await registry.register_node_pids("test-project", {5678})
        
        bundle = await registry.get_all_resources("test-project")
        
        assert bundle.process_info is not None
        assert bundle.process_info.wrapper_process is mock_process
        assert bundle.port == 3000
        assert task in bundle.tasks
        
        task.cancel()
    
    async def test_clear_resources(self, registry, mock_process):
        """Test clearing all resources for a project."""
        task = asyncio.create_task(asyncio.sleep(0.1))
        
        await registry.register_process("test-project", mock_process, port=3000)
        await registry.register_task("test-project", task)
        await registry.register_node_pids("test-project", {5678})
        
        # Verify resources exist
        assert "test-project" in registry.processes
        assert "test-project" in registry.tasks
        assert "test-project" in registry.ports
        assert "test-project" in registry.node_pids
        
        await registry.clear_resources("test-project")
        
        # Verify resources are cleared
        assert "test-project" not in registry.processes
        assert "test-project" not in registry.tasks
        assert "test-project" not in registry.ports
        assert "test-project" not in registry.node_pids
        
        task.cancel()
    
    async def test_get_all_project_names(self, registry, mock_process):
        """Test getting all project names."""
        task1 = asyncio.create_task(asyncio.sleep(0.1))
        task2 = asyncio.create_task(asyncio.sleep(0.1))
        
        await registry.register_process("project1", mock_process, port=3000)
        await registry.register_task("project2", task1)
        await registry.register_node_pids("project3", {5678})
        
        names = await registry.get_all_project_names()
        
        assert names == {"project1", "project2", "project3"}
        
        task1.cancel()
        task2.cancel()
    
    async def test_get_all_tasks(self, registry):
        """Test getting all registered tasks."""
        task1 = asyncio.create_task(asyncio.sleep(0.1))
        task2 = asyncio.create_task(asyncio.sleep(0.1))
        
        await registry.register_task("project1", task1)
        await registry.register_task("project2", task2)
        
        all_tasks = await registry.get_all_tasks()
        
        assert task1 in all_tasks
        assert task2 in all_tasks
        assert len(all_tasks) == 2
        
        task1.cancel()
        task2.cancel()
    
    async def test_remove_task(self, registry):
        """Test removing a specific task."""
        task1 = asyncio.create_task(asyncio.sleep(0.1))
        task2 = asyncio.create_task(asyncio.sleep(0.1))
        
        await registry.register_task("project1", task1)
        await registry.register_task("project1", task2)
        
        assert len(registry.tasks["project1"]) == 2
        
        await registry.remove_task("project1", task1)
        
        assert len(registry.tasks["project1"]) == 1
        assert task2 in registry.tasks["project1"]
        assert task1 not in registry.tasks["project1"]
        
        task1.cancel()
        task2.cancel()