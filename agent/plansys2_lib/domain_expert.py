import rclpy
from rclpy.node import Node

from plansys2_msgs.srv import GetDomain
from std_msgs.msg import Empty

class DomainExpert(Node):

    def __init__(self)->None:
        super().__init__('agent_domain_expert_client')
        self._get_domain_client = self.create_client(GetDomain, '/domain_expert/get_domain')
    
    def get_domain(self, timeout_sec:float=5.0)->tuple[bool, str, str]:

        client = self._get_domain_client
        if not client.wait_for_service(timeout_sec=timeout_sec):
            info=f"Service {client.srv_name} not available after waiting for {timeout_sec} seconds"
            self.get_logger().error(info)
            return False,"",info
        req = GetDomain.Request()
        req.request = Empty()
        future = client.call_async(req)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()

        if response is None:
            info=f"Service call to {client.srv_name} failed"
            self.get_logger().error(info)
            return False,"",info
        if not response.success:
            info=f"Service call to {client.srv_name} returned failure: {response.message}"
            self.get_logger().error(info)
            return False,"",info
        return True, response.domain, response.error_info