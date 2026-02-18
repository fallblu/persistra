import unittest
import os
import tempfile
import pandas as pd
import numpy as np
from src.persistra.core.project import Project, Node, Socket, Operation
from src.persistra.core.objects import DataWrapper, TimeSeries, IntParam
from src.persistra.core.io import save_project, load_project

# --- Mock Operations for Testing ---

class MockSourceOp(Operation):
    """Generates a simple integer."""
    name = "Mock Source"
    def __init__(self):
        super().__init__()
        self.outputs = [{'name': 'out', 'type': DataWrapper}]
        self.parameters = [IntParam('value', 'Value', default=10)]

    def execute(self, inputs, params):
        return {'out': DataWrapper(params['value'])}

class MockTransformOp(Operation):
    """Adds 5 to the input."""
    name = "Mock Transform"
    def __init__(self):
        super().__init__()
        self.inputs = [{'name': 'src', 'type': DataWrapper}]
        self.outputs = [{'name': 'result', 'type': DataWrapper}]

    def execute(self, inputs, params):
        val = inputs['src'].data
        return {'result': DataWrapper(val + 5)}

# --- Tests ---

class TestGraphCore(unittest.TestCase):
    
    def setUp(self):
        self.project = Project()
        self.node_a = Node(MockSourceOp)
        self.node_b = Node(MockTransformOp)
        self.project.add_node(self.node_a)
        self.project.add_node(self.node_b)

    def test_node_instantiation(self):
        """Test if nodes render sockets and parameters correctly."""
        self.assertEqual(len(self.node_a.output_sockets), 1)
        self.assertEqual(len(self.node_b.input_sockets), 1)
        self.assertEqual(self.node_a.parameters[0].value, 10)

    def test_connection_logic(self):
        """Test connecting two sockets."""
        sock_out = self.node_a.get_output_socket('out')
        sock_in = self.node_b.get_input_socket('src')
        
        # Connect
        sock_out.connect_to(sock_in)
        self.assertIn(sock_in, sock_out.connections)
        self.assertIn(sock_out, sock_in.connections)
        
        # Disconnect
        sock_out.disconnect(sock_in)
        self.assertNotIn(sock_in, sock_out.connections)

    def test_lazy_evaluation_flow(self):
        """Test the Pull (Compute) and Push (Invalidate) systems."""
        sock_out = self.node_a.get_output_socket('out')
        sock_in = self.node_b.get_input_socket('src')
        sock_out.connect_to(sock_in)

        # 1. Initial State: Dirty
        self.assertTrue(self.node_b._is_dirty)

        # 2. Compute (Pull)
        result = self.node_b.compute()
        self.assertEqual(result['result'].data, 15) # 10 + 5
        self.assertFalse(self.node_b._is_dirty) # Should be cached now

        # 3. Modify Upstream Parameter (Push Invalidation)
        self.node_a.set_parameter('value', 20)
        
        # Node A should be dirty
        self.assertTrue(self.node_a._is_dirty)
        # Node B (downstream) should have been invalidated automatically
        self.assertTrue(self.node_b._is_dirty)

        # 4. Re-compute
        result_new = self.node_b.compute()
        self.assertEqual(result_new['result'].data, 25) # 20 + 5

    def test_serialization(self):
        """Test saving and loading the project using Pickle."""
        sock_out = self.node_a.get_output_socket('out')
        sock_in = self.node_b.get_input_socket('src')
        sock_out.connect_to(sock_in)
        
        # Change a param to ensure state is saved
        self.node_a.set_parameter('value', 99)

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            save_project(self.project, tmp.name)
            loaded_project = load_project(tmp.name)
            
            # Verify structure
            self.assertEqual(len(loaded_project.nodes), 2)
            
            # Find the nodes (IDs will match)
            loaded_a = next(n for n in loaded_project.nodes if n.operation.name == "Mock Source")
            loaded_b = next(n for n in loaded_project.nodes if n.operation.name == "Mock Transform")
            
            # Verify param persistence
            self.assertEqual(loaded_a.parameters[0].value, 99)
            
            # Verify connection persistence
            out_socket = loaded_a.get_output_socket('out')
            in_socket = loaded_b.get_input_socket('src')
            self.assertIn(in_socket, out_socket.connections)
            
            tmp.close()
            os.unlink(tmp.name)

if __name__ == '__main__':
    unittest.main()
