import rclpy
from rclpy.node import Node

from niryo_plansys2_interfaces.srv import ObserveScene
from std_msgs.msg import Empty

class SceneObserver(Node):

    def __init__(self)->None:
        super().__init__('agent_scene_observer_client')
        self._observe_scene_client = self.create_client(ObserveScene, '/observe_scene')

    def observe_scene(self, timeout_sec:float=5.0)->tuple[bool, list, str]:
        client = self._observe_scene_client

        if not client.wait_for_service(timeout_sec=timeout_sec):
            info=f"Service {client.srv_name} not available after waiting for {timeout_sec} seconds"
            self.get_logger().error(info)
            return False, [], info
        
        req = ObserveScene.Request()
        req.request = Empty()
        future = client.call_async(req)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()

        if response is None:
            info=f"Service call to {client.srv_name} failed"
            self.get_logger().error(info)
            return False, [], info
        
        if not response.success:
            info=f"Service call to {client.srv_name} returned failure: {response.message}"
            self.get_logger().warn(info)
            return False, [], info
        
        objects = [(obj.name, obj.type, obj.location)for obj in response.objects]
        return True, objects, ""