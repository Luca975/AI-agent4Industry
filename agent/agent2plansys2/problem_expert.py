import rclpy
from rclpy.node import Node

from plansys2_msgs.srv import AddProblem, ClearProblemKnowledge
from std_msgs.msg import Empty

class ProblemExpert(Node):

    def __init__(self)->None:
        super().__init__('agent_problem_expert_client')
        self._add_client = self.create_client(AddProblem, '/problem_expert/add_problem')
        self._clear_knowledge_client = self.create_client(ClearProblemKnowledge, '/problem_expert/clear_problem_knowledge')

    def _call(self,client,request,timeout_sec:float=5.0)->tuple[bool, str]:
        if not client.wait_for_service(timeout_sec=timeout_sec):
            info=f"Service {client.srv_name} not available after waiting for {timeout_sec} seconds"
            self.get_logger().error(info)
            return False, info
        
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()

        if response is None:
            info=f"Service call to {client.srv_name} failed"
            self.get_logger().error(info)
            return False, info
        
        if not response.success:
            info=f"Service call to {client.srv_name} returned failure: {response.message}"
            self.get_logger().error(info)
        
        return response.success, response.error_info
    
    def add_problem(self,problem:str)->tuple[bool, str]:
        req = AddProblem.Request()
        req.problem = problem
        return self._call(self._add_client, req)

    def clear_problem_knowledge(self)->tuple[bool, str]:
        req = ClearProblemKnowledge.Request()
        req.request = Empty()
        return self._call(self._clear_knowledge_client, req)