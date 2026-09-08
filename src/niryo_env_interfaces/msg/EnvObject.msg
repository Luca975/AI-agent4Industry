# One object reported by the perception layer, carried in EnvScene.

string id   # unique id of this detected instance

# What the detector recognise (cube, person)
string class_id
float64 score   # detector confidence in [0,1]

# Empty when does not apply to the class (e.g. a person)
string color

# Pose of the object CENTRE
geometry_msgs/Pose pose

# Extent of the object along the axes of its own (oriented) pose
geometry_msgs/Vector3 size