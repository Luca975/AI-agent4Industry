# import rclpy
# from rclpy.node import Node

from plansys2_lib.base import PlanSys2ClientBase
from niryo_world_interfaces.srv import ObserveScene
from std_msgs.msg import Empty

class SceneObserver(PlanSys2ClientBase):

    def __init__(self)->None:
        super().__init__('agent_scene_observer_client')
        self._observe_scene_client = self.create_client(ObserveScene, '/world_model_server/observe_scene', callback_group=self.cb_group)

    def observe_scene(self, timeout_sec:float=5.0)->tuple[bool, list, list, str]:
        # client = self._observe_scene_client

        # if not client.wait_for_service(timeout_sec=timeout_sec):
        #     info=f"Service {client.srv_name} not available after waiting for {timeout_sec} seconds"
        #     self.get_logger().error(info)
        #     return False, [], info
        
        req = ObserveScene.Request()
        req.request = Empty()

        # future = client.call_async(req)
        # rclpy.spin_until_future_complete(self, future)
        # response = future.result()

        response = self._call_sync(self._observe_scene_client, req, timeout_sec)

        if response is None:
            info=f"Service call to {self._observe_scene_client.srv_name} failed"
            self.get_logger().error(info)
            return False, [], [], info
        
        if not response.success:
            info = response.error_info or f"Service {self._observe_scene_client.srv_name} returned failure without error_info"
            self.get_logger().warn(info)
            return False, [], [], info
        
        objects = [(obj.name, obj.type, obj.location, obj.held, obj.color)for obj in response.objects]
        paths = [(p.from_node, p.to_node, p.clear)for p in response.paths]
        return True, objects, paths, ""