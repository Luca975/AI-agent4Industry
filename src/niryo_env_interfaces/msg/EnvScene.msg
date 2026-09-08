# A full perception frame: everything detected at one instant, published on
# /env/scene by the perception node.

std_msgs/Header header      # stamp is used by consumers for freshness; frame_id of the poses
EnvObject[] objects         # detected objects; an empty list is valid (nothin detected)